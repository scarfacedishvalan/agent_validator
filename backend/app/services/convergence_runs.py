from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import statistics
from threading import Event, RLock, Thread
from typing import Any, Callable
from uuid import uuid4

from app.services.convergence_config import (
    ConfigurationConflict, ConfigurationStore, atomic_write, result_directory, strict_json,
)
from app.services.orchestrators.factor_view_orchestrator import generate_from_messages, validate_factor_view_response
from app.services.utils.aisuite_llm_client import AISuiteLLMClient

logger = logging.getLogger(__name__)
RUNNING = {"running", "stopping"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def diagnostic_rows(payload: dict[str, Any]) -> list[dict[str, float | None]]:
    factors = payload.get("factorOrder")
    responses = payload.get("responses")
    if not isinstance(factors, list) or not factors or not all(isinstance(f, str) for f in factors) or len(set(factors)) != len(factors):
        raise ValueError("Run has an invalid or empty factor order.")
    if not isinstance(responses, list):
        raise ValueError("Run responses must be an array.")
    rows = []
    context = None
    for response in responses:
        if not isinstance(response, dict) or response.get("factorOrder") != factors:
            raise ValueError("Response factor order does not match the run.")
        current_context = tuple(response.get(key) for key in ("asOf", "targetHorizon", "qReturnConvention"))
        if context is not None and context != current_context:
            raise ValueError("Response return context changed within the run.")
        context = current_context
        active, q = response.get("activeFactors"), response.get("Q")
        if not isinstance(active, list) or not all(isinstance(f, str) for f in active) or not isinstance(q, list):
            raise ValueError("Response activeFactors and Q must be arrays.")
        if len(active) != len(q) or len(set(active)) != len(active) or not set(active) <= set(factors):
            raise ValueError("Response activeFactors and Q are misaligned.")
        values = {}
        for factor, entry in zip(active, q, strict=True):
            if not isinstance(entry, list) or len(entry) != 1:
                raise ValueError("Q must be a column matrix.")
            value = entry[0]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("Q must contain finite numeric values.")
            values[factor] = value
        rows.append({factor: values.get(factor) for factor in factors})
    return rows


def diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    rows = diagnostic_rows(payload)
    summary = []
    series = {}
    for factor in payload["factorOrder"]:
        values = [row[factor] for row in rows]
        active: list[float] = []
        running_mean = []
        coverage = []
        mean = 0.0
        for index, value in enumerate(values, 1):
            if value is not None:
                active.append(value)
                count = len(active)
                mean = mean * ((count - 1) / count) + value / count
            running_mean.append(mean if active else None)
            coverage.append(len(active) / index)
        summary.append({
            "factor": factor, "active": len(active), "abstained": len(values) - len(active),
            "activeFraction": len(active) / len(values) if values else None,
            "mean": statistics.mean(active) if active else None,
            "sampleStd": statistics.stdev(active) if len(active) > 1 else None,
            "min": min(active) if active else None, "max": max(active) if active else None,
        })
        series[factor] = {"values": values, "runningMean": running_mean, "coverage": coverage}
    return {"rows": rows, "summary": summary, "series": series}


class ConvergenceRuns:
    """One local backend process owns one sequential, checkpointed batch at a time."""

    def __init__(
        self,
        store: ConfigurationStore,
        generate: Callable[..., dict[str, Any]] = generate_from_messages,
        client_factory: Callable[..., Any] = AISuiteLLMClient,
    ) -> None:
        self.store = store
        self.generate = generate
        self.client_factory = client_factory
        self.lock = RLock()
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.active: dict[str, Any] | None = None
        self.active_path: Path | None = None
        self.index_path = store.root / "backend" / "data" / "convergence_directories.json"
        self.closing = False

    def directories(self) -> set[Path]:
        directories = {self.store.root / "convergence_results"}
        if self.index_path.exists():
            entries = strict_json(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
                raise ValueError("Convergence directory index is malformed.")
            directories.update(result_directory(self.store.root, item) for item in entries)
        document = self.store.document("run")
        if not document["error"]:
            run = strict_json(document["content"])
            directories.add(result_directory(self.store.root, run["outputDirectory"]))
        return directories

    def register_directory(self, directory: Path) -> None:
        directories = self.directories() | {directory}
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.index_path, json.dumps(sorted(str(path.relative_to(self.store.root)) for path in directories), indent=2) + "\n")

    def paths(self) -> list[Path]:
        paths = []
        for directory in self.directories():
            if directory.exists():
                for path in directory.glob("factor_views_*.json"):
                    if path.is_file() and path.resolve().is_relative_to(self.store.root):
                        paths.append(path)
        return sorted(set(paths), key=lambda path: path.name, reverse=True)

    def recover(self) -> None:
        for path in self.paths():
            try:
                payload = self.read_path(path)
                if payload.get("schemaVersion") == 2 and payload.get("status") in RUNNING:
                    payload.update(status="interrupted", complete=False, finishedAt=now(),
                                   error="Backend stopped before this batch finished. Start a new run to make more calls.")
                    self.checkpoint(path, payload)
            except (OSError, ValueError):
                logger.exception("Could not recover convergence file %s", path)

    def read_path(self, path: Path) -> dict[str, Any]:
        payload = strict_json(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Run file must contain a JSON object.")
        diagnostic_rows(payload)
        for key in ("name", "model", "personalityKey", "error", "persistenceError", "provenanceWarning"):
            if key in payload and payload[key] is not None and not isinstance(payload[key], str):
                raise ValueError(f"Run {key} must be a string.")
        snapshot = payload.get("evidenceSnapshot")
        if snapshot is not None and (
            not isinstance(snapshot, dict)
            or not isinstance(snapshot.get("values"), dict)
        ):
            raise ValueError("Run evidenceSnapshot must contain a values object.")
        if not isinstance(payload.get("startedAt"), str):
            raise ValueError("Run startedAt must be an ISO timestamp.")
        datetime.fromisoformat(payload["startedAt"].replace("Z", "+00:00"))
        if not isinstance(payload.get("complete"), bool):
            raise ValueError("Run complete must be a boolean.")
        if "log" in payload and (
            not isinstance(payload["log"], list)
            or any(
                not isinstance(entry, dict) or not isinstance(entry.get("at"), str)
                or not isinstance(entry.get("message"), str)
                for entry in payload["log"]
            )
        ):
            raise ValueError("Run log entries must contain timestamp and message strings.")
        for response in payload["responses"]:
            validate_factor_view_response(
                response, contract={},
                evidence_snapshot=snapshot if snapshot is not None else {"asOf": response.get("asOf")},
                target_horizon=response.get("targetHorizon"),
                q_return_convention=response.get("qReturnConvention"),
                factor_definitions=[{"key": key} for key in payload["factorOrder"]],
            )
        completed = payload.get("completedIterations")
        requested = payload.get("requestedIterations")
        if isinstance(completed, bool) or not isinstance(completed, int) or completed != len(payload["responses"]):
            raise ValueError("Run completed count does not match its responses.")
        if isinstance(requested, bool) or not isinstance(requested, int) or requested < completed or requested < 1:
            raise ValueError("Run requested count is invalid.")
        if payload.get("complete") is True and completed != requested:
            raise ValueError("Complete run does not contain all requested responses.")
        payload["id"] = path.name
        payload["outputPath"] = str(path)
        payload["legacy"] = payload.get("schemaVersion") != 2
        if not payload["legacy"] and payload.get("status") not in ("running", "stopping", "completed", "stopped", "failed", "interrupted"):
            raise ValueError("Run has an invalid lifecycle status.")
        if not payload["legacy"] and payload["complete"] != (payload["status"] == "completed"):
            raise ValueError("Run completion flag does not match its lifecycle status.")
        if payload["legacy"]:
            payload["status"] = "completed" if payload.get("complete") else "incomplete"
            payload["provenanceWarning"] = "Legacy notebook run: frozen templates and configuration provenance are unavailable."
        return payload

    def checkpoint(self, path: Path, payload: dict[str, Any]) -> None:
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

    def list_runs(self) -> dict[str, Any]:
        runs, issues = [], []
        with self.lock:
            active = deepcopy(self.active)
        if active and active["status"] not in RUNNING and not active.get("persistenceError"):
            active = None
        active_id = active["id"] if active else None
        for path in self.paths():
            if path.name == active_id:
                continue
            try:
                runs.append(self.summary(self.read_path(path)))
            except (OSError, ValueError) as exc:
                issues.append({"path": str(path), "error": str(exc)})
        if active:
            runs.insert(0, self.summary(active))
        runs.sort(key=lambda item: item.get("startedAt", ""), reverse=True)
        return {"runs": runs, "issues": issues}

    @staticmethod
    def summary(payload: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "name", "status", "startedAt", "finishedAt", "requestedIterations",
                "completedIterations", "complete", "model", "personalityKey", "outputPath", "error",
                "persistenceError", "legacy")
        return {key: payload.get(key) for key in keys}

    def get(self, run_id: str) -> dict[str, Any]:
        if Path(run_id).name != run_id or not run_id.startswith("factor_views_") or not run_id.endswith(".json"):
            raise LookupError("Invalid run ID.")
        with self.lock:
            if (
                self.active and self.active["id"] == run_id
                and (self.active["status"] in RUNNING or self.active.get("persistenceError"))
            ):
                payload = deepcopy(self.active)
            else:
                matches = [path for path in self.paths() if path.name == run_id]
                if len(matches) != 1:
                    raise LookupError("Run was not found or its filename is ambiguous.")
                payload = self.read_path(matches[0])
        return {**payload, "diagnostics": diagnostics(payload)}

    def start(self, revisions: dict[str, str]) -> dict[str, Any]:
        with self.lock:
            if self.closing:
                raise ConfigurationConflict("Backend is shutting down.")
            if self.thread and self.thread.is_alive():
                raise ConfigurationConflict("A convergence batch is already running.")
            frozen = self.store.freeze(revisions)
            config = frozen["configuration"]
            run = config["run"]
            # Client construction validates credentials before creating a running batch; no API call.
            client = self.client_factory(model=run["model"])
            directory = result_directory(self.store.root, run["outputDirectory"])
            directory.mkdir(parents=True, exist_ok=True)
            self.register_directory(directory)
            filename = f"factor_views_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex}.json"
            path = directory / filename
            payload = {
                "schemaVersion": 2, "id": filename, "name": run["name"], "status": "running",
                "startedAt": now(), "finishedAt": None, "requestedIterations": run["iterations"],
                "completedIterations": 0, "complete": False, "personalityKey": run["personality"],
                "model": run["model"], "factorOrder": [item["key"] for item in config["factors"]],
                "evidenceSnapshot": deepcopy(config["evidence"]), "frozen": frozen,
                "responses": [], "log": [], "error": None, "outputPath": str(path), "legacy": False,
            }
            with path.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.active = payload
            self.active_path = path
            self.stop_event = Event()
            self.thread = Thread(target=self.execute, args=(payload, path, client), daemon=True, name="convergence-batch")
            try:
                self.thread.start()
            except RuntimeError as exc:
                payload.update(status="failed", complete=False, finishedAt=now(), error=f"Could not start batch worker: {exc}")
                self.checkpoint(path, payload)
                raise
            return self.summary(payload)

    def stop(self, run_id: str) -> dict[str, Any]:
        with self.lock:
            if not self.active or self.active["id"] != run_id or self.active["status"] not in RUNNING:
                raise ConfigurationConflict("This run is not active.")
            self.stop_event.set()
            self.active["status"] = "stopping"
            if self.active_path is not None:
                self.checkpoint(self.active_path, self.active)
            return self.summary(self.active)

    def shutdown(self) -> None:
        with self.lock:
            self.closing = True
            self.stop_event.set()
        if self.thread and self.thread.is_alive():
            # Finish the current bounded provider request and checkpoint before shutdown.
            self.thread.join()

    def execute(self, payload: dict[str, Any], path: Path, client: Any) -> None:
        config = payload["frozen"]["configuration"]
        try:
            for iteration in range(1, payload["requestedIterations"] + 1):
                if self.stop_event.is_set():
                    break
                response = self.generate(
                    deepcopy(payload["frozen"]["messages"]), contract=deepcopy(config["contract"]),
                    evidence_snapshot=deepcopy(config["evidence"]), defaults=deepcopy(config["defaults"]),
                    factor_definitions=deepcopy(config["factors"]), model=payload["model"], llm_client=client,
                )
                with self.lock:
                    # Check invariants even for injected clients before the successful-call checkpoint.
                    validate_factor_view_response(
                        response, contract=config["contract"], evidence_snapshot=config["evidence"],
                        target_horizon=config["defaults"]["target_horizon"],
                        q_return_convention=config["defaults"]["q_return_convention"],
                        factor_definitions=config["factors"],
                    )
                    candidate = {**payload, "responses": [*payload["responses"], response]}
                    diagnostic_rows(candidate)
                    payload["responses"].append(response)
                    payload["completedIterations"] = iteration
                    payload["log"].append({"at": now(), "iteration": iteration, "active": len(response["activeFactors"]),
                                           "message": f"Call {iteration}/{payload['requestedIterations']} validated."})
                    self.checkpoint(path, payload)
            with self.lock:
                completed = payload["completedIterations"] == payload["requestedIterations"]
                payload["status"] = "completed" if completed else "interrupted" if self.closing else "stopped"
                payload["complete"] = completed
                payload["finishedAt"] = now()
                self.checkpoint(path, payload)
        except Exception as exc:
            # Worker boundary: failures are logged, persisted and exposed, never retried/skipped.
            logger.exception("Convergence batch %s failed", payload["id"])
            with self.lock:
                description = f"{type(exc).__name__}: {exc}"
                key = os.environ.get("OPENAI_API_KEY", "")
                if key:
                    description = description.replace(key, "[REDACTED]")
                payload.update(status="failed", complete=False, finishedAt=now(), error=description)
                payload["log"].append({"at": now(), "message": "Batch failed. No automatic retry was made."})
                try:
                    self.checkpoint(path, payload)
                except OSError as persistence_error:
                    logger.exception("Convergence failure checkpoint could not be written: %s", path)
                    payload["persistenceError"] = str(persistence_error)

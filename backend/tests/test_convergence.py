from copy import deepcopy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.convergence_config import (
    ConfigurationConflict, ConfigurationStore, DOCUMENT_PATHS, PROJECT_ROOT,
    resolve_configuration, strict_json, validate_document,
)
from app.services.convergence_runs import ConvergenceRuns, diagnostics
from app.services.orchestrators.factor_view_orchestrator import generate_from_messages


class ConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        for relative in DOCUMENT_PATHS.values():
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / relative, destination)
        self.store = ConfigurationStore(self.root)
        self.example = strict_json(self.store.document("contract")["content"])["example"]
        self.manager = ConvergenceRuns(self.store, client_factory=Mock(return_value=object()))

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def revisions(self):
        return {key: item["revision"] for key, item in self.store.documents().items()}

    def set_run(self, **changes):
        doc = self.store.document("run")
        value = strict_json(doc["content"])
        value.update(changes)
        self.store.save("run", json.dumps(value), doc["revision"])

    def join(self):
        self.assertIsNotNone(self.manager.thread)
        self.manager.thread.join(5)
        self.assertFalse(self.manager.thread.is_alive())

    def test_preview_renders_complete_inputs_without_calling_provider(self):
        preview = self.store.freeze(self.revisions())
        self.assertIn("OUTPUT_JSON_SCHEMA:", preview["messages"][0]["content"])
        self.assertIn("SHARED FINANCIAL GROUNDING POLICY", preview["messages"][0]["content"])
        self.assertIn('"HML_return_1m": -0.032', preview["messages"][1]["content"])
        selected_personality = preview["configuration"]["run"]["personality"]
        self.assertIn(selected_personality, preview["messages"][1]["content"])
        for instruction in preview["configuration"]["personalities"][selected_personality]:
            self.assertIn(instruction.strip(), preview["messages"][1]["content"])
        self.manager.client_factory.assert_not_called()

    def test_compare_and_swap_preserves_external_edits(self):
        doc = self.store.document("policy")
        self.store.path("policy").write_text("Externally changed policy", encoding="utf-8")
        with self.assertRaises(ConfigurationConflict):
            self.store.save("policy", "My stale edit", doc["revision"])
        self.assertEqual(self.store.document("policy")["content"], "Externally changed policy")
        latest = self.store.document("policy")
        saved = self.store.save("policy", "Explicit overwrite", latest["revision"])
        self.assertEqual(saved["content"], "Explicit overwrite")
        self.assertNotEqual(saved["revision"], doc["revision"])

    def test_invalid_file_is_reported_and_blocks_freeze(self):
        self.store.path("evidence").write_text("{bad", encoding="utf-8")
        self.assertTrue(self.store.document("evidence")["error"])
        with self.assertRaises(ValueError):
            self.store.freeze(self.revisions())

    def test_stale_start_revisions_are_rejected(self):
        revisions = self.revisions()
        doc = self.store.document("policy")
        self.store.save("policy", "Updated policy", doc["revision"])
        with self.assertRaises(ConfigurationConflict):
            self.store.freeze(revisions)

    def test_rejects_invalid_documents_and_unsafe_paths(self):
        cases = [
            ("run", {**strict_json(self.store.document("run")["content"]), "iterations": True}),
            ("run", {**strict_json(self.store.document("run")["content"]), "iterations": 0}),
            ("run", {**strict_json(self.store.document("run")["content"]), "outputDirectory": ".."}),
            ("defaults", {"target_horizon": "12 months", "q_return_convention": "excess", "q_min": .2, "q_max": .1}),
            ("contract", {"type": "object", "properties": {}, "$ref": "https://example.invalid/schema"}),
            ("personalities", {"empty": []}),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_document(key, json.dumps(value), self.root)
        for text in ('{"a": 1, "a": 2}', '{"value": NaN}', '{"value": 1e999}'):
            with self.assertRaises(ValueError):
                strict_json(text)
        with self.assertRaises(LookupError):
            self.store.document("../secrets")
        for template in ("{unknown}", "{", "{evidence_snapshot_json.__class__}"):
            with self.assertRaises(ValueError):
                validate_document("user", template, self.root)

    def test_cross_document_references_are_validated(self):
        contents = {key: doc["content"] for key, doc in self.store.documents().items()}
        contents["run"] = json.dumps({**strict_json(contents["run"]), "personality": "missing"})
        with self.assertRaisesRegex(ValueError, "personality"):
            resolve_configuration(contents, self.root)
        contents["run"] = self.store.document("run")["content"]
        catalog = strict_json(contents["factors"])
        catalog[0]["evidence_metric_keys"] = ["undefined_metric"]
        contents["factors"] = json.dumps(catalog)
        with self.assertRaisesRegex(ValueError, "unknown metrics"):
            resolve_configuration(contents, self.root)

    def test_model_choices_and_selection_sync_through_document_api_and_execution(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        app.state.convergence_runs = self.manager
        self.manager.generate = Mock(return_value=deepcopy(self.example))
        with TestClient(app) as client:
            route = "/api/v1/convergence/config/documents/run"
            document = client.get("/api/v1/convergence/config/documents").json()["documents"]["run"]
            settings = strict_json(document["content"])
            settings.update(models=["openai:gpt-6-astra", "openai:gpt-5.6-terra"],
                            model="openai:gpt-5.6-terra", temperature=None, iterations=1)
            saved = client.put(route, json={"content": json.dumps(settings), "revision": document["revision"]})
            self.assertEqual(saved.status_code, 200, saved.text)
            reloaded = client.get("/api/v1/convergence/config/documents").json()["documents"]["run"]
            self.assertEqual(strict_json(reloaded["content"]), settings)
            self.assertEqual(strict_json(self.store.path("run").read_text()), settings)
            # An external edit is visible through the same read path without restarting.
            settings["model"] = "openai:gpt-6-astra"
            self.store.path("run").write_text(json.dumps(settings), encoding="utf-8")
            external = client.get("/api/v1/convergence/config/documents").json()["documents"]["run"]
            self.assertNotEqual(external["revision"], saved.json()["revision"])
            self.assertEqual(strict_json(external["content"])["model"], "openai:gpt-6-astra")
            created = client.post("/api/v1/convergence/runs",
                                  json={"confirmLiveCalls": True, "revisions": self.revisions()})
            self.assertEqual(created.status_code, 201, created.text)
            self.join()
            self.manager.client_factory.assert_called_once_with(model="openai:gpt-6-astra", temperature=None)
            detail = self.manager.get(created.json()["id"])
            self.assertEqual(detail["model"], settings["model"])
            self.assertEqual(detail["frozen"]["configuration"]["run"]["models"], settings["models"])

    def test_model_list_validation_rejects_invalid_choices_and_preserves_file(self):
        document = self.store.document("run")
        settings = strict_json(document["content"])
        for changes in (
            {"models": []},
            {"models": ["openai:gpt-6-astra", "openai:gpt-6-astra"]},
            {"models": ["gpt-6-astra"]},
            {"models": [False]},
            {"models": ["openai:gpt-6-astra"], "model": "openai:missing"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.save("run", json.dumps({**settings, **changes}), document["revision"])
            self.assertEqual(self.store.document("run")["revision"], document["revision"])

    def test_complete_run_has_frozen_messages_and_atomic_checkpoints(self):
        self.set_run(iterations=2)
        calls = []
        def generate(messages, **_kwargs):
            calls.append(deepcopy(messages))
            if len(calls) == 1:
                doc = self.store.document("policy")
                self.store.save("policy", "New policy for the next batch", doc["revision"])
            return deepcopy(self.example)
        self.manager.generate = generate
        created = self.manager.start(self.revisions())
        self.join()
        detail = self.manager.get(created["id"])
        self.assertEqual(detail["status"], "completed")
        self.assertTrue(detail["complete"])
        self.assertEqual(detail["completedIterations"], 2)
        self.assertEqual(calls[0], calls[1])
        self.assertNotIn("New policy for the next batch", calls[1][0]["content"])
        saved = strict_json(Path(detail["outputPath"]).read_text(encoding="utf-8"))
        self.assertEqual(len(saved["responses"]), 2)
        self.assertEqual(saved["frozen"]["messages"], calls[0])
        self.assertFalse(list(Path(detail["outputPath"]).parent.glob("*.tmp")))
        second = self.manager.start(self.revisions())
        self.join()
        self.assertNotEqual(second["id"], created["id"])

    def test_failure_keeps_completed_calls_and_does_not_retry(self):
        self.set_run(iterations=3)
        generate = Mock(side_effect=[deepcopy(self.example), ValueError("invalid output")])
        self.manager.generate = generate
        with self.assertLogs("app.services.convergence_runs", level="ERROR"):
            created = self.manager.start(self.revisions())
            self.join()
        detail = self.manager.get(created["id"])
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["completedIterations"], 1)
        self.assertFalse(detail["complete"])
        self.assertIn("invalid output", detail["error"])
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(len(strict_json(Path(detail["outputPath"]).read_text())["responses"]), 1)

    def test_checkpoint_failure_is_not_reported_as_success(self):
        self.set_run(iterations=1)
        self.manager.generate = Mock(return_value=deepcopy(self.example))
        with patch.object(self.manager, "checkpoint", side_effect=OSError("disk unavailable")):
            with self.assertLogs("app.services.convergence_runs", level="ERROR"):
                created = self.manager.start(self.revisions())
                self.join()
        detail = self.manager.get(created["id"])
        self.assertEqual(detail["status"], "failed")
        self.assertFalse(detail["complete"])
        self.assertIn("disk unavailable", detail["persistenceError"])
        self.assertEqual(len(detail["responses"]), 1)

    def test_provider_error_does_not_expose_the_api_key_in_results(self):
        self.set_run(iterations=1)
        self.manager.generate = Mock(side_effect=RuntimeError("Rejected test-secret-value"))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret-value"}):
            with self.assertLogs("app.services.convergence_runs", level="ERROR"):
                created = self.manager.start(self.revisions())
                self.join()
        detail = self.manager.get(created["id"])
        self.assertNotIn("test-secret-value", detail["error"])
        self.assertIn("[REDACTED]", detail["error"])

    def test_stop_finishes_inflight_call_and_rejects_concurrent_start(self):
        self.set_run(iterations=3)
        entered, release = Event(), Event()
        def generate(*_args, **_kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test timed out waiting for release.")
            return deepcopy(self.example)
        self.manager.generate = generate
        created = self.manager.start(self.revisions())
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(ConfigurationConflict):
                self.manager.start(self.revisions())
            self.manager.stop(created["id"])
        finally:
            release.set()
        self.join()
        detail = self.manager.get(created["id"])
        self.assertEqual(detail["status"], "stopped")
        self.assertEqual(detail["completedIterations"], 1)

    def test_recovery_marks_previous_running_batch_interrupted(self):
        self.set_run(iterations=1)
        self.manager.generate = Mock(return_value=deepcopy(self.example))
        created = self.manager.start(self.revisions())
        self.join()
        path = Path(self.manager.get(created["id"])["outputPath"])
        payload = strict_json(path.read_text())
        payload.update(status="running", complete=False)
        path.write_text(json.dumps(payload), encoding="utf-8")
        restarted = ConvergenceRuns(self.store)
        restarted.recover()
        self.assertEqual(restarted.get(created["id"])["status"], "interrupted")

    def test_legacy_runs_and_invalid_files_are_explicit(self):
        directory = self.root / "convergence_results"
        directory.mkdir()
        payload = {"startedAt": "2026-10-01T00:00:00Z", "requestedIterations": 1, "completedIterations": 1,
                   "complete": True, "factorOrder": self.example["factorOrder"], "responses": [self.example]}
        (directory / "factor_views_legacy.json").write_text(json.dumps(payload), encoding="utf-8")
        (directory / "factor_views_broken.json").write_text("{bad", encoding="utf-8")
        listing = self.manager.list_runs()
        self.assertEqual(len(listing["runs"]), 1)
        self.assertEqual(len(listing["issues"]), 1)
        detail = self.manager.get("factor_views_legacy.json")
        self.assertTrue(detail["legacy"])
        self.assertIn("unavailable", detail["provenanceWarning"])

    def test_diagnostics_map_active_factors_not_positions_and_exclude_abstentions(self):
        def response(active, q):
            return {"factorOrder": ["A", "B", "C"], "activeFactors": active,
                    "Q": [[v] for v in q], "asOf": "2026-10-01",
                    "targetHorizon": "12 months", "qReturnConvention": "annualized excess return"}
        payload = {"factorOrder": ["A", "B", "C"], "responses": [
            response(["B", "A"], [.04, .02]), response(["A"], [.06]), response([], []),
        ]}
        result = diagnostics(payload)
        self.assertEqual(result["rows"][0], {"A": .02, "B": .04, "C": None})
        a, b, c = result["summary"]
        self.assertAlmostEqual(a["mean"], .04)
        self.assertAlmostEqual(a["sampleStd"], .0282842712474619)
        self.assertEqual(a["activeFraction"], 2 / 3)
        self.assertIsNone(b["sampleStd"])
        self.assertIsNone(c["mean"])
        self.assertEqual(c["active"], 0)
        self.assertEqual(result["series"]["A"]["runningMean"], [.02, .04, .04])
        self.assertEqual(result["series"]["C"]["runningMean"], [None, None, None])
        self.assertEqual(result["series"]["B"]["coverage"], [1, .5, 1 / 3])

    def test_frozen_generator_enforces_bounds_and_context(self):
        frozen = self.store.freeze(self.revisions())
        config = frozen["configuration"]
        config["defaults"]["q_max"] = .01
        client = Mock()
        client.complete.return_value = json.dumps(self.example)
        with self.assertRaisesRegex(ValueError, "upper bound"):
            generate_from_messages(
                frozen["messages"], contract=config["contract"], evidence_snapshot=config["evidence"],
                defaults=config["defaults"], factor_definitions=config["factors"],
                model="openai:test", llm_client=client,
            )

    def test_routes_support_document_save_preview_and_revision_conflicts(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        with TestClient(app) as client:
            response = client.get("/api/v1/convergence/config/documents")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("OPENAI_API_KEY", response.text)
            docs = response.json()["documents"]
            contents = {key: doc["content"] for key, doc in docs.items()}
            preview = client.post("/api/v1/convergence/preview", json={"documents": contents})
            self.assertEqual(preview.status_code, 200, preview.text)
            saved = client.put("/api/v1/convergence/config/documents/policy",
                               json={"content": "New grounding rules", "revision": docs["policy"]["revision"]})
            self.assertEqual(saved.status_code, 200)
            conflict = client.put("/api/v1/convergence/config/documents/policy",
                                  json={"content": "Stale edit", "revision": docs["policy"]["revision"]})
            self.assertEqual(conflict.status_code, 409)
            rejected = client.post("/api/v1/convergence/runs",
                                   json={"confirmLiveCalls": False, "revisions": self.revisions()})
            self.assertEqual(rejected.status_code, 422)
            self.assertEqual(client.get("/api/v1/convergence/runs/missing").status_code, 404)
            app.state.convergence_runs = self.manager
            self.manager.generate = Mock(return_value=deepcopy(self.example))
            self.set_run(iterations=1)
            started = client.post("/api/v1/convergence/runs",
                                  json={"confirmLiveCalls": True, "revisions": self.revisions()})
            self.assertEqual(started.status_code, 201, started.text)
            self.join()
            detail = client.get(f"/api/v1/convergence/runs/{started.json()['id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["status"], "completed")

    def test_run_history_endpoint_includes_completed_runs_and_invalid_file_issues(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        app.state.convergence_runs = self.manager
        self.set_run(iterations=1)
        self.manager.generate = Mock(return_value=deepcopy(self.example))
        with TestClient(app) as client:
            empty = client.get("/api/v1/convergence/runs")
            self.assertEqual(empty.status_code, 200, empty.text)
            self.assertEqual(empty.json(), {"runs": [], "issues": []})
            created = client.post("/api/v1/convergence/runs",
                                  json={"confirmLiveCalls": True, "revisions": self.revisions()})
            self.assertEqual(created.status_code, 201, created.text)
            self.join()
            broken = self.root / "convergence_results" / "factor_views_invalid.json"
            broken.write_text("{bad", encoding="utf-8")
            listing = client.get("/api/v1/convergence/runs")
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertEqual(len(listing.json()["runs"]), 1)
            run = listing.json()["runs"][0]
            self.assertEqual(run["id"], created.json()["id"])
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["completedIterations"], 1)
            self.assertNotIn("responses", run)
            self.assertEqual(len(listing.json()["issues"]), 1)
            self.assertEqual(listing.json()["issues"][0]["path"], str(broken))

    def test_stop_endpoint_finishes_inflight_call_and_rejects_inactive_runs(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        app.state.convergence_runs = self.manager
        self.set_run(iterations=3)
        entered, release = Event(), Event()
        def generate(*_args, **_kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test timed out waiting for release.")
            return deepcopy(self.example)
        self.manager.generate = Mock(side_effect=generate)
        with TestClient(app) as client:
            created = client.post("/api/v1/convergence/runs",
                                  json={"confirmLiveCalls": True, "revisions": self.revisions()})
            self.assertEqual(created.status_code, 201, created.text)
            run_id = created.json()["id"]
            try:
                self.assertTrue(entered.wait(5))
                concurrent = client.post("/api/v1/convergence/runs",
                                         json={"confirmLiveCalls": True, "revisions": self.revisions()})
                self.assertEqual(concurrent.status_code, 409, concurrent.text)
                stopping = client.post(f"/api/v1/convergence/runs/{run_id}/stop")
                self.assertEqual(stopping.status_code, 200, stopping.text)
                self.assertEqual(stopping.json()["status"], "stopping")
                self.assertEqual(stopping.json()["completedIterations"], 0)
                listing = client.get("/api/v1/convergence/runs")
                self.assertEqual(listing.json()["runs"][0]["status"], "stopping")
            finally:
                release.set()
            self.join()
            detail = client.get(f"/api/v1/convergence/runs/{run_id}")
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["status"], "stopped")
            self.assertEqual(detail.json()["completedIterations"], 1)
            self.assertFalse(detail.json()["complete"])
            self.assertEqual(self.manager.generate.call_count, 1)
            self.assertEqual(client.post(f"/api/v1/convergence/runs/{run_id}/stop").status_code, 409)
            self.assertEqual(client.post("/api/v1/convergence/runs/unknown/stop").status_code, 409)

    def test_events_endpoint_streams_initial_state_and_external_file_changes(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        app.state.convergence_runs = self.manager
        store = app.state.convergence_store
        original_documents = store.documents
        calls = 0
        def documents_with_external_edit():
            nonlocal calls
            calls += 1
            if calls == 2:
                store.path("policy").write_text("Externally edited policy", encoding="utf-8")
            return original_documents()
        with TestClient(app) as client:
            with (
                patch("app.api.routers.convergence.Request.is_disconnected",
                      new=AsyncMock(side_effect=[False, False, True])),
                patch("app.api.routers.convergence.asyncio.sleep", new=AsyncMock()),
                patch.object(store, "documents", side_effect=documents_with_external_edit),
            ):
                response = client.get("/api/v1/convergence/events")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("text/event-stream", response.headers["content-type"])
            self.assertEqual(response.headers["cache-control"], "no-cache")
            self.assertEqual(response.headers["x-accel-buffering"], "no")
            frames = [frame for frame in response.text.split("\n\n") if frame.startswith("event: changed")]
            self.assertEqual(len(frames), 2, response.text)
            states = [json.loads(frame.split("\ndata: ", 1)[1]) for frame in frames]
            self.assertEqual(set(states[0]["documents"]), set(DOCUMENT_PATHS))
            self.assertNotEqual(states[0]["documents"]["policy"], states[1]["documents"]["policy"])
            self.assertEqual(states[1]["documents"]["policy"], store.document("policy")["revision"])
            self.assertEqual(states[0]["runs"], {"runs": [], "issues": []})
            self.manager.client_factory.assert_not_called()

    def test_events_endpoint_reports_read_error_and_recovers(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        app.state.convergence_runs = self.manager
        store = app.state.convergence_store
        snapshot = store.documents()
        with TestClient(app) as client:
            with (
                patch("app.api.routers.convergence.Request.is_disconnected",
                      new=AsyncMock(side_effect=[False, False, True])),
                patch("app.api.routers.convergence.asyncio.sleep", new=AsyncMock()),
                patch.object(store, "documents", side_effect=[OSError("temporarily unreadable"), snapshot]),
                self.assertLogs("app.api.routers.convergence", level="ERROR"),
            ):
                response = client.get("/api/v1/convergence/events")
            self.assertEqual(response.status_code, 200)
            frames = response.text.strip().split("\n\n")
            self.assertTrue(frames[0].startswith("event: sync-error"), response.text)
            self.assertEqual(json.loads(frames[0].split("\ndata: ", 1)[1]),
                             {"error": "temporarily unreadable"})
            self.assertTrue(frames[1].startswith("event: changed"), response.text)

    def test_document_and_preview_routes_reject_invalid_payloads_without_writing(self):
        app = create_app(self.root / "test.sqlite", convergence_root=self.root)
        with TestClient(app) as client:
            docs = client.get("/api/v1/convergence/config/documents").json()["documents"]
            revision = docs["defaults"]["revision"]
            invalid = client.put("/api/v1/convergence/config/documents/defaults",
                                 json={"content": "{bad", "revision": revision})
            self.assertEqual(invalid.status_code, 422, invalid.text)
            self.assertEqual(self.store.document("defaults")["revision"], revision)
            unknown = client.put("/api/v1/convergence/config/documents/unknown",
                                 json={"content": "value", "revision": "missing"})
            self.assertEqual(unknown.status_code, 404, unknown.text)
            self.assertEqual(client.post("/api/v1/convergence/preview",
                                         json={"documents": {}}).status_code, 422)
            contents = {key: doc["content"] for key, doc in docs.items()}
            contents["user"] = "{unknown}"
            self.assertEqual(client.post("/api/v1/convergence/preview",
                                         json={"documents": contents}).status_code, 422)
            stale = client.post("/api/v1/convergence/runs",
                                json={"confirmLiveCalls": True, "revisions": {}})
            self.assertEqual(stale.status_code, 409, stale.text)


if __name__ == "__main__":
    unittest.main()

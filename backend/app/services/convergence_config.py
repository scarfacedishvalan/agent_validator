from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from string import Formatter
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from jsonschema.exceptions import SchemaError

from app.schemas.evidence import MetricDefinition
from app.services.factor_view_prompts import (
    render_factor_view_system_prompt,
    render_factor_view_user_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCUMENT_PATHS = {
    "run": "backend/fixtures/convergence_run_settings.json",
    "evidence": "backend/fixtures/evidence_snapshot_example.json",
    "personalities": "backend/fixtures/personalities.json",
    "defaults": "backend/fixtures/factor_view_defaults.json",
    "factors": "backend/fixtures/factor_definitions.json",
    "metrics": "backend/fixtures/metric_definitions.json",
    "system": "backend/prompts/system_prompt.txt",
    "user": "backend/prompts/user_prompt.txt",
    "policy": "backend/prompts/shared_financial_grounding_policy.txt",
    "contract": "backend/fixtures/factor_view_output_contract.json",
}
TEXT_IDS = {"system", "user", "policy"}
COMMON_FIELDS = {
    "target_horizon", "q_return_convention", "q_min", "q_max",
    "factor_definitions_json", "metric_definitions_json",
}
STRING = {"type": "string", "minLength": 1, "pattern": r"\S"}
NUMBER = {"type": "number"}


class ConfigurationConflict(ValueError):
    pass


def strict_json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(text, object_pairs_hook=pairs)
    json.dumps(value, allow_nan=False)
    return value


def object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def result_directory(root: Path, configured: str) -> Path:
    directory = (root / configured).resolve()
    if directory == root.resolve() or not directory.is_relative_to(root.resolve()):
        raise ValueError("Results directory must be a subdirectory of the project.")
    if directory.exists() and not directory.is_dir():
        raise ValueError("Results directory points to an existing file.")
    return directory


def validate_document(document_id: str, content: str, root: Path = PROJECT_ROOT) -> Any:
    if document_id not in DOCUMENT_PATHS:
        raise LookupError("Unknown configuration document.")
    if not content.strip():
        raise ValueError("Document must not be blank.")
    if document_id in TEXT_IDS:
        if document_id != "policy":
            allowed = COMMON_FIELDS | (
                {"shared_financial_grounding_policy"} if document_id == "system"
                else {"agent_personality", "evidence_snapshot_json"}
            )
            fields = set()
            for _, field, spec, conversion in Formatter().parse(content):
                if field is not None:
                    if field not in allowed or spec or conversion:
                        raise ValueError(f"Unsupported template placeholder: {field}")
                    fields.add(field)
            essential = {"shared_financial_grounding_policy"} if document_id == "system" else {"agent_personality", "evidence_snapshot_json"}
            if not essential <= fields:
                raise ValueError(f"Template must include: {', '.join(sorted(essential))}")
        return content
    value = strict_json(content)
    schemas = {
        "run": object_schema({
            "name": STRING, "iterations": {"type": "integer", "minimum": 1},
            "personality": STRING, "model": {**STRING, "pattern": r"^[^:\s]+:[^\s]+$"},
            "models": {"type": "array", "minItems": 1, "uniqueItems": True,
                       "items": {**STRING, "pattern": r"^openai:[^\s:]+$"}},
            "outputDirectory": STRING, "temperature": {"type": ["number", "null"], "minimum": 0, "maximum": 2},
        }, ["name", "iterations", "personality", "model", "models", "outputDirectory"]),
        "evidence": object_schema({
            "name": STRING, "asOf": {"type": "string", "format": "date"},
            "values": {"type": "object", "additionalProperties": NUMBER},
        }, ["name", "asOf", "values"]),
        "defaults": object_schema({
            "target_horizon": STRING, "q_return_convention": STRING,
            "q_min": {"type": ["number", "null"]}, "q_max": {"type": ["number", "null"]},
        }, ["target_horizon", "q_return_convention", "q_min", "q_max"]),
        "personalities": {
            "type": "object", "minProperties": 1, "propertyNames": STRING,
            "additionalProperties": {"type": "array", "minItems": 1, "items": STRING},
        },
        "factors": {
            "type": "array", "minItems": 1,
            "items": object_schema({
                "key": STRING, "name": STRING, "description": STRING,
                "positive_direction": STRING,
                "evidence_metric_keys": {"type": "array", "items": STRING, "uniqueItems": True},
            }, ["key", "name", "description", "positive_direction", "evidence_metric_keys"]),
        },
        "metrics": {"type": "array", "minItems": 1, "items": {"type": "object"}},
        "contract": {"type": "object", "required": ["type", "properties"],
                     "properties": {"type": {"const": "object"}, "properties": {"type": "object"}}},
    }
    try:
        Draft202012Validator(schemas[document_id], format_checker=FormatChecker()).validate(value)
    except ValidationError as exc:
        raise ValueError(f"{'/'.join(map(str, exc.absolute_path)) or document_id}: {exc.message}") from exc
    if document_id == "run":
        result_directory(root, value["outputDirectory"])
        if value["model"] not in value["models"]:
            raise ValueError("Selected model must be included in models.")
    if document_id == "defaults":
        if value["q_min"] is not None and value["q_max"] is not None and value["q_min"] > value["q_max"]:
            raise ValueError("Q minimum must not exceed maximum.")
    if document_id in {"factors", "metrics"}:
        keys = []
        for item in value:
            if document_id == "metrics":
                MetricDefinition.model_validate(item, strict=True)
            keys.append(item["key"])
        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise ValueError("Catalog keys must be non-blank strings.")
        if len(set(keys)) != len(keys):
            raise ValueError("Catalog keys must be unique.")
    if document_id == "contract":
        # No network/file references: schema editing must not trigger outbound reads.
        def check_references(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    if key in {"$ref", "$dynamicRef"} and (not isinstance(child, str) or not child.startswith("#")):
                        raise ValueError("Only local fragment schema references are supported.")
                    check_references(child)
            elif isinstance(node, list):
                for child in node:
                    check_references(child)
        check_references(value)
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError(f"Invalid output JSON Schema: {exc.message}") from exc
    return value


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ConfigurationStore:
    def __init__(self, root: Path = PROJECT_ROOT) -> None:
        self.root = root.resolve()
        self.lock = RLock()

    def path(self, document_id: str) -> Path:
        if document_id not in DOCUMENT_PATHS:
            raise LookupError("Unknown configuration document.")
        path = (self.root / DOCUMENT_PATHS[document_id]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Configuration paths must stay inside the project.")
        return path

    def document(self, document_id: str) -> dict[str, Any]:
        path = self.path(document_id)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {"id": document_id, "path": str(path), "content": "", "revision": "missing",
                    "error": "Source file is missing."}
        revision = hashlib.sha256(raw).hexdigest()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return {"id": document_id, "path": str(path), "content": "", "revision": revision,
                    "error": "Source file is not valid UTF-8."}
        error = None
        try:
            validate_document(document_id, content, self.root)
        except ValueError as exc:
            error = str(exc)
        return {"id": document_id, "path": str(path), "content": content, "revision": revision, "error": error}

    def documents(self) -> dict[str, dict[str, Any]]:
        with self.lock:
            return {document_id: self.document(document_id) for document_id in DOCUMENT_PATHS}

    def save(self, document_id: str, content: str, revision: str) -> dict[str, Any]:
        validate_document(document_id, content, self.root)
        with self.lock:
            if self.document(document_id)["revision"] != revision:
                raise ConfigurationConflict("File changed since it was loaded. Reload or explicitly overwrite the latest revision.")
            atomic_write(self.path(document_id), content)
            return self.document(document_id)

    def freeze(self, revisions: Mapping[str, str]) -> dict[str, Any]:
        with self.lock:
            docs = self.documents()
            if set(revisions) != set(docs) or any(revisions[key] != doc["revision"] for key, doc in docs.items()):
                raise ConfigurationConflict("Configuration changed. Wait for file sync and review the updated preview.")
            invalid = [f"{key}: {doc['error']}" for key, doc in docs.items() if doc["error"]]
            if invalid:
                raise ValueError("; ".join(invalid))
            frozen = resolve_configuration({key: doc["content"] for key, doc in docs.items()}, self.root)
            # Detect external writes during the multi-file read/render.
            if any(self.document(key)["revision"] != doc["revision"] for key, doc in docs.items()):
                raise ConfigurationConflict("Files changed while preparing the run. Review and retry.")
            frozen["sourceDocuments"] = docs
            return frozen


def resolve_configuration(contents: Mapping[str, str], root: Path = PROJECT_ROOT) -> dict[str, Any]:
    if set(contents) != set(DOCUMENT_PATHS):
        raise ValueError("A complete set of configuration documents is required.")
    config = {key: validate_document(key, text, root) for key, text in contents.items()}
    run = config["run"]
    if run["personality"] not in config["personalities"]:
        raise ValueError("Selected personality is not in the personality library.")
    metric_keys = {item["key"] for item in config["metrics"]}
    for factor in config["factors"]:
        unknown = set(factor["evidence_metric_keys"]) - metric_keys
        if unknown:
            raise ValueError(f"{factor['key']} references unknown metrics: {', '.join(sorted(unknown))}")
    unknown_evidence = set(config["evidence"]["values"]) - metric_keys
    if unknown_evidence:
        raise ValueError(f"Evidence has undefined metrics: {', '.join(sorted(unknown_evidence))}")
    defaults = config["defaults"]
    defaults["target_horizon"] = defaults["target_horizon"].strip()
    defaults["q_return_convention"] = defaults["q_return_convention"].strip()
    common = dict(
        target_horizon=defaults["target_horizon"], q_return_convention=defaults["q_return_convention"],
        q_min=defaults["q_min"], q_max=defaults["q_max"],
        factor_definitions=config["factors"], metric_definitions=config["metrics"],
    )
    system = render_factor_view_system_prompt(
        **common, template_text=config["system"], shared_financial_grounding_policy=config["policy"],
    )
    system += "\n\nOUTPUT_JSON_SCHEMA:\n" + json.dumps(config["contract"], ensure_ascii=False, indent=2, allow_nan=False)
    user = render_factor_view_user_prompt(
        **common, evidence_snapshot=config["evidence"], template_text=config["user"],
        personality_key=run["personality"],
        personality_instructions="\n".join(line.strip() for line in config["personalities"][run["personality"]]),
    )
    return {"configuration": config, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user},
    ]}

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.services.convergence_config import ConfigurationConflict, ConfigurationStore, resolve_configuration
from app.services.convergence_runs import ConvergenceRuns

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/convergence", tags=["convergence"])


class SaveDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(max_length=2_000_000)
    revision: str


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: dict[str, str]


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revisions: dict[str, str]
    confirmLiveCalls: bool


def services(request: Request) -> tuple[ConfigurationStore, ConvergenceRuns]:
    return request.app.state.convergence_store, request.app.state.convergence_runs


def api_error(exc: Exception) -> HTTPException:
    description = str(exc)
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        description = description.replace(key, "[REDACTED]")
    if isinstance(exc, ConfigurationConflict):
        return HTTPException(409, detail=description)
    if isinstance(exc, LookupError):
        return HTTPException(404, detail=description)
    if isinstance(exc, ValueError):
        return HTTPException(422, detail=description)
    logger.error("Convergence operation failed", exc_info=exc)
    return HTTPException(500, detail=f"Convergence operation failed: {description}")


@router.get("/config/documents")
def get_documents(request: Request) -> dict[str, Any]:
    store, _ = services(request)
    try:
        return {"documents": store.documents(), "credentialsReady": bool(os.environ.get("OPENAI_API_KEY", "").strip())}
    except (OSError, ValueError) as exc:
        raise api_error(exc) from exc


@router.put("/config/documents/{document_id}")
def put_document(document_id: str, payload: SaveDocument, request: Request) -> dict[str, Any]:
    store, _ = services(request)
    try:
        return store.save(document_id, payload.content, payload.revision)
    except (OSError, ValueError, LookupError) as exc:
        raise api_error(exc) from exc


@router.post("/preview")
def preview(payload: PreviewRequest, request: Request) -> dict[str, Any]:
    store, _ = services(request)
    try:
        return resolve_configuration(payload.documents, store.root)
    except (OSError, ValueError) as exc:
        raise api_error(exc) from exc


@router.get("/runs")
def list_runs(request: Request) -> dict[str, Any]:
    _, runs = services(request)
    try:
        return runs.list_runs()
    except (OSError, ValueError) as exc:
        raise api_error(exc) from exc


@router.post("/runs", status_code=201)
def start_run(payload: StartRequest, request: Request) -> dict[str, Any]:
    if not payload.confirmLiveCalls:
        raise HTTPException(422, detail="Explicit confirmation of billable live calls is required.")
    _, runs = services(request)
    try:
        return runs.start(payload.revisions)
    except (OSError, ValueError, RuntimeError) as exc:
        raise api_error(exc) from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    _, runs = services(request)
    try:
        return runs.get(run_id)
    except (OSError, ValueError, LookupError) as exc:
        raise api_error(exc) from exc


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, request: Request) -> dict[str, Any]:
    _, runs = services(request)
    try:
        return runs.stop(run_id)
    except (OSError, ValueError) as exc:
        raise api_error(exc) from exc


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    store, runs = services(request)

    async def stream():
        previous = None
        ticks = 0
        while not await request.is_disconnected():
            try:
                # Poll content hashes, not mtimes: handles external edits and atomic file replacement.
                docs = await asyncio.to_thread(store.documents)
                listing = await asyncio.to_thread(runs.list_runs)
                state = {"documents": {key: doc["revision"] for key, doc in docs.items()},
                         "runs": listing}
                serialized = json.dumps(state, ensure_ascii=False, allow_nan=False)
                if serialized != previous:
                    yield f"event: changed\ndata: {serialized}\n\n"
                    previous = serialized
                elif ticks % 15 == 0:
                    yield ": heartbeat\n\n"
            except (OSError, ValueError) as exc:
                logger.exception("Convergence change feed failed")
                yield f"event: sync-error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                previous = None
            ticks += 1
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })

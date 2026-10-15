from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.evidence import router as evidence_router
from app.api.routers.health import router as health_router
from app.api.routers.mutation_profiles import router as mutation_profiles_router
from app.api.routers.variants import router as variants_router
from app.config import DEFAULT_METRIC_CATALOG_PATH, get_database_path
from app.db.connection import initialize_database
from app.services.workbench import load_metric_catalog


def create_app(
    database_path: Path | None = None,
    metric_catalog_path: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        initialize_database(application.state.database_path)
        load_metric_catalog(application.state.metric_catalog_path)
        yield

    application = FastAPI(
        title="Agent Experiment Workbench API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.database_path = database_path or get_database_path()
    application.state.metric_catalog_path = metric_catalog_path or DEFAULT_METRIC_CATALOG_PATH
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(evidence_router)
    application.include_router(mutation_profiles_router)
    application.include_router(variants_router)
    return application


app = create_app()

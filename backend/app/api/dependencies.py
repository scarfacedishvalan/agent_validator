from pathlib import Path

from fastapi import Request


def get_database_path(request: Request) -> Path:
    return request.app.state.database_path


def get_metric_catalog_path(request: Request) -> Path:
    return request.app.state.metric_catalog_path

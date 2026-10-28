"""Health, readiness and safe metadata."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from trafiqon import __version__
from trafiqon.api import deps
from trafiqon.api.schemas import AlgorithmInfo, HealthResponse
from trafiqon.optimization import ALGORITHMS
from trafiqon.persistence.db import ping
from trafiqon.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["health"])


def _db_status(request: Request) -> str:
    st = deps.state(request)
    if st.engine is None:
        return "not_configured"
    return "ok" if ping(st.engine) else "unavailable"


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Liveness: the API process is up. Dependency status is reported, not required."""
    return HealthResponse(
        status="ok",
        version=__version__,
        api_version="v1",
        dependencies={"database": {"status": _db_status(request)}},
    )


@router.get("/ready", responses={503: {"description": "a required dependency is unavailable"}})
def ready(request: Request) -> JSONResponse:
    """Readiness: 200 only if the database is configured and reachable."""
    status = _db_status(request)
    ok = status == "ok"
    return JSONResponse(
        {"ready": ok, "dependencies": {"database": {"status": status}}},
        status_code=200 if ok else 503,
    )


@router.get("/algorithms", response_model=list[AlgorithmInfo], tags=["meta"])
def algorithms() -> list[AlgorithmInfo]:
    return [
        AlgorithmInfo(id=a.id, version=a.version, uses_seed=a.uses_seed, defaults=dict(a.defaults))
        for a in ALGORITHMS.values()
    ]


@router.get("/meta", tags=["meta"])
def meta(settings: Settings = Depends(deps.settings)) -> dict[str, Any]:
    """Safe application metadata: version and request limits (no secrets or URLs)."""
    return {"version": __version__, "api_version": "v1", "limits": asdict(settings.limits)}

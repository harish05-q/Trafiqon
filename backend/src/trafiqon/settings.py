"""Runtime settings for the API and worker, from environment variables (see .env.example).

Core packages (domain, routing, optimization, ...) never read settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Limits:
    max_nodes: int = 2_000
    max_edges: int = 10_000
    max_customers: int = 200
    max_vehicles: int = 50
    max_time_limit_s: float = 120.0
    max_sa_iterations: int = 2_000_000
    max_qpso_swarm: int = 100
    max_qpso_iterations: int = 2_000
    max_queued_runs: int = 200
    max_suite_runs: int = 100
    max_export_runs: int = 1_000
    max_progress_events_per_run: int = 200
    page_size_max: int = 100

    @classmethod
    def from_env(cls) -> Limits:
        d = cls()
        return cls(
            **{
                k: type(getattr(d, k))(os.environ.get(f"TRAFIQON_LIMIT_{k.upper()}", getattr(d, k)))
                for k in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    limits: Limits = field(default_factory=Limits)
    # Worker
    worker_poll_interval_s: float = 0.5
    heartbeat_interval_s: float = 1.0
    stale_after_s: float = 30.0
    max_attempts: int = 2  # an interrupted run is re-queued at most (max_attempts - 1) times
    progress_event_min_interval_s: float = 0.5
    event_retention_days: int = 30
    # SSE
    sse_poll_interval_s: float = 0.5
    sse_max_duration_s: float = 600.0

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("TRAFIQON_CORS_ORIGINS")
        return cls(
            database_url=os.environ.get("TRAFIQON_DATABASE_URL") or None,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
            if origins
            else cls.cors_origins,
            limits=Limits.from_env(),
            worker_poll_interval_s=_float("TRAFIQON_WORKER_POLL_INTERVAL_S", 0.5),
            heartbeat_interval_s=_float("TRAFIQON_HEARTBEAT_INTERVAL_S", 1.0),
            stale_after_s=_float("TRAFIQON_STALE_AFTER_S", 30.0),
            max_attempts=_int("TRAFIQON_MAX_ATTEMPTS", 2),
            progress_event_min_interval_s=_float("TRAFIQON_PROGRESS_EVENT_MIN_INTERVAL_S", 0.5),
            event_retention_days=_int("TRAFIQON_EVENT_RETENTION_DAYS", 30),
        )

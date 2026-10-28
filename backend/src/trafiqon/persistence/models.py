"""SQLAlchemy 2 models. Schema changes go through Alembic (persistence/migrations)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL = frozenset({RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED})
ACTIVE = frozenset({RunStatus.RUNNING, RunStatus.CANCELLING})


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class ScenarioRow(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # Ownership boundary for future auth; NULL = shared/local.
    owner_id: Mapped[str | None] = mapped_column(String(200), index=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "scenario_versions.id",
            use_alter=True,
            name="fk_scenarios_current_version",
            ondelete="SET NULL",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScenarioVersionRow(Base):
    """Immutable: a DB trigger rejects UPDATE (see migration 0001)."""

    __tablename__ = "scenario_versions"
    __table_args__ = (UniqueConstraint("scenario_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    node_count: Mapped[int] = mapped_column(Integer)
    edge_count: Mapped[int] = mapped_column(Integer)
    customer_count: Mapped[int] = mapped_column(Integer)
    vehicle_count: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkSuiteRow(Base):
    __tablename__ = "benchmark_suites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenario_versions.id", ondelete="RESTRICT"), index=True
    )
    specs: Mapped[list[Any]] = mapped_column(JSONB)
    seeds: Mapped[list[Any]] = mapped_column(JSONB)
    repetitions: Mapped[int] = mapped_column(Integer)
    budget_policy: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str | None] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class RunRow(Base):
    __tablename__ = "optimization_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','CANCELLING','CANCELLED','COMPLETED','FAILED')",
            name="ck_runs_status",
        ),
        Index("ix_runs_queue", "status", "created_at"),
        Index("ix_runs_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenario_versions.id", ondelete="RESTRICT"), index=True
    )
    suite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("benchmark_suites.id", ondelete="CASCADE"), index=True
    )
    suite_spec: Mapped[str | None] = mapped_column(String(200))
    repetition: Mapped[int | None] = mapped_column(Integer)
    algorithm_id: Mapped[str] = mapped_column(String(100), index=True)
    algorithm_version: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    seed: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.QUEUED)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str | None] = mapped_column(String(200), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    termination_reason: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class RunResultRow(Base):
    """One per run (PK = run_id): a duplicate result insert is rejected by the database."""

    __tablename__ = "run_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("optimization_runs.id", ondelete="CASCADE"), primary_key=True
    )
    feasible: Mapped[bool] = mapped_column(Boolean)
    objective: Mapped[float | None] = mapped_column(Float)
    total_distance: Mapped[float | None] = mapped_column(Float)
    solution: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    iterations: Mapped[int] = mapped_column(Integer)
    evaluations: Mapped[int | None] = mapped_column(BigInteger)
    elapsed_s: Mapped[float] = mapped_column(Float)
    time_to_first_feasible_s: Mapped[float | None] = mapped_column(Float)
    termination_reason: Mapped[str] = mapped_column(String(50))
    optimality: Mapped[str] = mapped_column(String(30))
    seed: Mapped[int | None] = mapped_column(BigInteger)
    history: Mapped[list[Any]] = mapped_column(JSONB)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEventRow(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_id_id", "run_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("optimization_runs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))  # lifecycle | progress
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

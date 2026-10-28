"""Optimization-run, result and event persistence (reads and run creation).

State transitions after creation live in `worker.queue.PostgresJobQueue`, all as conditional
UPDATEs so a terminal state can never be overwritten.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trafiqon.persistence.models import (
    RunEventRow,
    RunResultRow,
    RunRow,
    RunStatus,
    ScenarioVersionRow,
)


def request_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def add_event(
    session: Session, run_id: uuid.UUID, kind: str, type_: str, payload: dict[str, Any]
) -> RunEventRow:
    row = RunEventRow(run_id=run_id, kind=kind, type=type_, payload=payload)
    session.add(row)
    session.flush()
    return row


def find_by_idempotency_key(session: Session, key: str) -> RunRow | None:
    return session.scalar(select(RunRow).where(RunRow.idempotency_key == key))


def new_run(
    *,
    scenario_version_id: uuid.UUID,
    algorithm_id: str,
    algorithm_version: str,
    config: dict[str, Any],
    seed: int | None,
    max_attempts: int,
    idempotency_key: str | None = None,
    fingerprint: str = "",
    suite_id: uuid.UUID | None = None,
    suite_spec: str | None = None,
    repetition: int | None = None,
    owner_id: str | None = None,
) -> RunRow:
    return RunRow(
        id=uuid.uuid4(),
        scenario_version_id=scenario_version_id,
        algorithm_id=algorithm_id,
        algorithm_version=algorithm_version,
        config=config,
        seed=seed,
        status=RunStatus.QUEUED,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        suite_id=suite_id,
        suite_spec=suite_spec,
        repetition=repetition,
        owner_id=owner_id,
        attempt=0,
        max_attempts=max_attempts,
    )


def count_queued(session: Session) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(RunRow).where(RunRow.status == RunStatus.QUEUED)
        )
        or 0
    )


@dataclass(frozen=True)
class RunFilter:
    status: str | None = None
    algorithm_id: str | None = None
    scenario_version_id: uuid.UUID | None = None
    suite_id: uuid.UUID | None = None
    scenario_id: uuid.UUID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


def list_runs(
    session: Session, flt: RunFilter, limit: int, offset: int
) -> tuple[list[RunRow], int]:
    query = select(RunRow)
    if flt.status:
        query = query.where(RunRow.status == flt.status)
    if flt.algorithm_id:
        query = query.where(RunRow.algorithm_id == flt.algorithm_id)
    if flt.scenario_version_id:
        query = query.where(RunRow.scenario_version_id == flt.scenario_version_id)
    if flt.suite_id:
        query = query.where(RunRow.suite_id == flt.suite_id)
    if flt.scenario_id:
        versions = select(ScenarioVersionRow.id).where(
            ScenarioVersionRow.scenario_id == flt.scenario_id
        )
        query = query.where(RunRow.scenario_version_id.in_(versions))
    if flt.created_after:
        query = query.where(RunRow.created_at >= flt.created_after)
    if flt.created_before:
        query = query.where(RunRow.created_at < flt.created_before)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(RunRow.created_at.desc(), RunRow.id).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def get_result(session: Session, run_id: uuid.UUID) -> RunResultRow | None:
    return session.get(RunResultRow, run_id)


def events_after(
    session: Session, run_id: uuid.UUID, after_id: int, limit: int = 500
) -> list[RunEventRow]:
    return list(
        session.scalars(
            select(RunEventRow)
            .where(RunEventRow.run_id == run_id, RunEventRow.id > after_id)
            .order_by(RunEventRow.id)
            .limit(limit)
        ).all()
    )

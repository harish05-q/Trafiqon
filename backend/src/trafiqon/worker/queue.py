"""Job queue interface and its PostgreSQL implementation (decision D1 in STATUS.md).

The `optimization_runs` row IS the queue entry: enqueueing is inserting a QUEUED row in the
caller's transaction, so the database and the queue cannot diverge (no outbox needed).

Delivery is at-least-once: a worker that stalls past `stale_after_s` can have its run
re-queued while it is still executing. Ownership (`worker_id`) makes the stale worker's
later heartbeat/complete/fail calls no-ops, so only one result is ever stored (plus the
run_results primary key rejects duplicates). Exactly-once execution is NOT claimed.

Every transition is a single conditional UPDATE; terminal states never change.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from trafiqon.persistence.db import session_scope
from trafiqon.persistence.models import ACTIVE, RunResultRow, RunRow, RunStatus
from trafiqon.persistence.runs import add_event


@dataclass(frozen=True)
class ClaimedRun:
    id: uuid.UUID
    scenario_version_id: uuid.UUID
    algorithm_id: str
    config: dict[str, Any]
    seed: int | None
    attempt: int


class JobQueue(Protocol):
    def enqueue(self, session: Session, run: RunRow) -> None: ...
    def claim(self, worker_id: str) -> ClaimedRun | None: ...
    def heartbeat(self, run_id: uuid.UUID, worker_id: str) -> RunStatus | None: ...
    def report_progress(
        self, run_id: uuid.UUID, worker_id: str, progress: dict[str, Any], write_event: bool
    ) -> bool: ...
    def complete(
        self, run_id: uuid.UUID, worker_id: str, result: dict[str, Any]
    ) -> RunStatus | None: ...
    def fail(
        self, run_id: uuid.UUID, worker_id: str, error: dict[str, Any]
    ) -> RunStatus | None: ...
    def request_cancel(self, session: Session, run_id: uuid.UUID) -> RunStatus | None: ...
    def recover_stale(self) -> list[tuple[uuid.UUID, RunStatus]]: ...


ACTIVE_VALUES = tuple(s.value for s in ACTIVE)


class PostgresJobQueue:
    def __init__(self, factory: sessionmaker[Session], *, stale_after_s: float = 30.0) -> None:
        self.factory = factory
        self.stale_after_s = stale_after_s

    # -- API side (caller's transaction) ---------------------------------------------------

    def enqueue(self, session: Session, run: RunRow) -> None:
        run.status = RunStatus.QUEUED
        session.add(run)
        session.flush()
        add_event(session, run.id, "lifecycle", "queued", {"status": RunStatus.QUEUED})

    def request_cancel(self, session: Session, run_id: uuid.UUID) -> RunStatus | None:
        """QUEUED -> CANCELLED; RUNNING -> CANCELLING; anything else unchanged. Idempotent.
        Returns the status after the request, or None if the run does not exist."""
        status = session.execute(
            text(
                """
                UPDATE optimization_runs SET
                  status = CASE WHEN status = 'QUEUED' THEN 'CANCELLED' ELSE 'CANCELLING' END,
                  cancel_requested_at = COALESCE(cancel_requested_at, now()),
                  finished_at = CASE WHEN status = 'QUEUED' THEN now() ELSE finished_at END,
                  termination_reason = CASE WHEN status = 'QUEUED' THEN 'cancelled'
                                            ELSE termination_reason END
                WHERE id = :id AND status IN ('QUEUED', 'RUNNING')
                RETURNING status
                """
            ),
            {"id": run_id},
        ).scalar()
        if status is not None:
            add_event(
                session,
                run_id,
                "lifecycle",
                "cancelled" if status == RunStatus.CANCELLED else "cancel_requested",
                {"status": status},
            )
            return RunStatus(status)
        current = session.scalar(select(RunRow.status).where(RunRow.id == run_id))
        return RunStatus(current) if current else None

    # -- worker side (own transactions) ----------------------------------------------------

    def claim(self, worker_id: str) -> ClaimedRun | None:
        with session_scope(self.factory) as s:
            row = s.execute(
                text(
                    """
                    UPDATE optimization_runs SET
                      status = 'RUNNING', worker_id = :w, attempt = attempt + 1,
                      started_at = now(), heartbeat_at = now()
                    WHERE id = (
                      SELECT id FROM optimization_runs WHERE status = 'QUEUED'
                      ORDER BY created_at, id
                      FOR UPDATE SKIP LOCKED LIMIT 1
                    )
                    RETURNING id, scenario_version_id, algorithm_id, config, seed, attempt
                    """
                ),
                {"w": worker_id},
            ).first()
            if row is None:
                return None
            add_event(
                s,
                row.id,
                "lifecycle",
                "started",
                {"status": RunStatus.RUNNING, "worker_id": worker_id, "attempt": row.attempt},
            )
            return ClaimedRun(
                row.id, row.scenario_version_id, row.algorithm_id, row.config, row.seed, row.attempt
            )

    def heartbeat(self, run_id: uuid.UUID, worker_id: str) -> RunStatus | None:
        """Refresh the heartbeat. Returns RUNNING/CANCELLING, or None if this worker no
        longer owns the run (re-queued, failed by recovery, ...)."""
        with session_scope(self.factory) as s:
            status = s.execute(
                text(
                    "UPDATE optimization_runs SET heartbeat_at = now() "
                    "WHERE id = :id AND worker_id = :w AND status IN ('RUNNING','CANCELLING') "
                    "RETURNING status"
                ),
                {"id": run_id, "w": worker_id},
            ).scalar()
            return RunStatus(status) if status else None

    def report_progress(
        self, run_id: uuid.UUID, worker_id: str, progress: dict[str, Any], write_event: bool
    ) -> bool:
        with session_scope(self.factory) as s:
            updated = s.execute(
                update(RunRow)
                .where(
                    RunRow.id == run_id,
                    RunRow.worker_id == worker_id,
                    RunRow.status.in_(ACTIVE_VALUES),
                )
                .values(progress=progress)
                .returning(RunRow.id)
            ).scalar()
            if updated and write_event:
                add_event(s, run_id, "progress", "progress", progress)
            return updated is not None

    def complete(
        self, run_id: uuid.UUID, worker_id: str, result: dict[str, Any]
    ) -> RunStatus | None:
        """Store the result and finish the run in ONE transaction. A run that was being
        cancelled (or whose algorithm stopped on cancellation) ends CANCELLED, never
        COMPLETED. Returns the terminal status, or None if this worker lost ownership."""
        with session_scope(self.factory) as s:
            status = s.execute(
                text(
                    """
                    UPDATE optimization_runs SET
                      status = CASE WHEN status = 'CANCELLING' OR :reason = 'cancelled'
                                    THEN 'CANCELLED' ELSE 'COMPLETED' END,
                      finished_at = now(), termination_reason = :reason
                    WHERE id = :id AND worker_id = :w AND status IN ('RUNNING','CANCELLING')
                    RETURNING status
                    """
                ),
                {"id": run_id, "w": worker_id, "reason": result["termination_reason"]},
            ).scalar()
            if status is None:
                return None
            s.execute(
                insert(RunResultRow)
                .values(run_id=run_id, **result)
                .on_conflict_do_nothing(index_elements=["run_id"])
            )
            add_event(
                s,
                run_id,
                "lifecycle",
                status.lower(),
                {
                    "status": status,
                    "feasible": result["feasible"],
                    "objective": result["objective"],
                    "termination_reason": result["termination_reason"],
                },
            )
            return RunStatus(status)

    def fail(self, run_id: uuid.UUID, worker_id: str, error: dict[str, Any]) -> RunStatus | None:
        with session_scope(self.factory) as s:
            status = s.execute(
                text(
                    "UPDATE optimization_runs SET status = 'FAILED', finished_at = now(), "
                    "termination_reason = 'error', error = CAST(:err AS JSONB) "
                    "WHERE id = :id AND worker_id = :w AND status IN ('RUNNING','CANCELLING') "
                    "RETURNING status"
                ),
                {"id": run_id, "w": worker_id, "err": _json(error)},
            ).scalar()
            if status is None:
                return None
            add_event(s, run_id, "lifecycle", "failed", {"status": status, "error": error})
            return RunStatus(status)

    def recover_stale(self) -> list[tuple[uuid.UUID, RunStatus]]:
        """Handle runs whose worker stopped heart-beating:
        CANCELLING -> CANCELLED; RUNNING with attempts left -> QUEUED (bounded retry);
        RUNNING with no attempts left -> FAILED (worker_lost)."""
        out: list[tuple[uuid.UUID, RunStatus]] = []
        with session_scope(self.factory) as s:
            rows = s.execute(
                text(
                    """
                    SELECT id, status, attempt, max_attempts, worker_id FROM optimization_runs
                    WHERE status IN ('RUNNING','CANCELLING')
                      AND heartbeat_at < now() - make_interval(secs => :stale)
                    ORDER BY heartbeat_at FOR UPDATE SKIP LOCKED
                    """
                ),
                {"stale": self.stale_after_s},
            ).all()
            for r in rows:
                lost = {
                    "code": "worker_lost",
                    "worker_id": r.worker_id,
                    "attempt": r.attempt,
                    "message": f"no heartbeat for more than {self.stale_after_s:g}s",
                }
                if r.status == RunStatus.CANCELLING:
                    new, sql = (
                        RunStatus.CANCELLED,
                        (
                            "status='CANCELLED', finished_at=now(), "
                            "termination_reason='cancelled', error=CAST(:err AS JSONB)"
                        ),
                    )
                elif r.attempt < r.max_attempts:
                    new, sql = (
                        RunStatus.QUEUED,
                        (
                            "status='QUEUED', worker_id=NULL, started_at=NULL, heartbeat_at=NULL, "
                            "progress=NULL, error=CAST(:err AS JSONB)"
                        ),
                    )
                else:
                    new, sql = (
                        RunStatus.FAILED,
                        (
                            "status='FAILED', finished_at=now(), termination_reason='worker_lost', "
                            "error=CAST(:err AS JSONB)"
                        ),
                    )
                s.execute(
                    text(f"UPDATE optimization_runs SET {sql} WHERE id = :id"),
                    {"id": r.id, "err": _json(lost)},
                )
                event = {
                    RunStatus.QUEUED: "requeued",
                    RunStatus.FAILED: "failed",
                    RunStatus.CANCELLED: "cancelled",
                }[new]
                add_event(s, r.id, "lifecycle", event, {"status": new, "error": lost})
                out.append((r.id, new))
        return out

    def prune_progress_events(self, older_than_days: int) -> int:
        """Delete progress events of finished runs older than the retention window.
        Lifecycle events are kept."""
        with session_scope(self.factory) as s:
            return s.execute(
                text(
                    """
                    DELETE FROM run_events e USING optimization_runs r
                    WHERE e.run_id = r.id AND e.kind = 'progress'
                      AND r.status IN ('COMPLETED','CANCELLED','FAILED')
                      AND e.created_at < now() - make_interval(days => :d)
                    """
                ),
                {"d": older_than_days},
            ).rowcount


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, default=str)

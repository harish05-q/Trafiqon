"""Worker process: claims queued runs and executes them outside the API process.

    uv run python -m trafiqon.worker.main [--migrate] [--once]

One run at a time per process; concurrency is bounded by the number of worker processes.
A heartbeat thread refreshes ownership every `heartbeat_interval_s` and turns a CANCELLING
status (or lost ownership) into the algorithm's cooperative cancel signal.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import Mapping

from trafiqon.experiments.runner import software_versions
from trafiqon.optimization import ALGORITHMS, Algorithm, AlgorithmInput, ProgressEvent
from trafiqon.persistence.db import make_engine, make_session_factory, migrate, session_scope
from trafiqon.persistence.models import RunStatus
from trafiqon.persistence.scenarios import get_version, load_version_scenario
from trafiqon.settings import Settings
from trafiqon.worker.queue import ClaimedRun, JobQueue, PostgresJobQueue
from trafiqon.worker.serialize import json_safe, result_to_row

log = logging.getLogger("trafiqon.worker")


class _Cancel:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.lost_ownership = False

    def is_cancelled(self) -> bool:
        return self.event.is_set()


class Worker:
    def __init__(
        self,
        factory,
        queue: JobQueue,
        settings: Settings,
        *,
        worker_id: str | None = None,
        algorithms: Mapping[str, Algorithm] | None = None,
    ) -> None:
        self.factory = factory
        self.queue = queue
        self.settings = settings
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.algorithms = algorithms if algorithms is not None else ALGORITHMS
        self.software = software_versions()

    def run_once(self) -> RunStatus | None:
        """Claim and execute at most one run. Returns its final status (None if idle or
        ownership was lost)."""
        claim = self.queue.claim(self.worker_id)
        if claim is None:
            return None
        return self._execute(claim)

    def run_forever(self, stop: threading.Event) -> None:
        last_recovery = last_prune = 0.0
        while not stop.is_set():
            now = time.monotonic()
            if now - last_recovery >= self.settings.stale_after_s / 2:
                for run_id, status in self.queue.recover_stale():
                    log.warning("recovered stale run %s -> %s", run_id, status)
                last_recovery = now
            if now - last_prune >= 3600 and isinstance(self.queue, PostgresJobQueue):
                self.queue.prune_progress_events(self.settings.event_retention_days)
                last_prune = now
            if self.run_once() is None:
                stop.wait(self.settings.worker_poll_interval_s)

    def _execute(self, claim: ClaimedRun) -> RunStatus | None:
        log.info("run %s: start (%s, attempt %d)", claim.id, claim.algorithm_id, claim.attempt)
        cancel = _Cancel()
        done = threading.Event()

        def beat() -> bool:
            status = self.queue.heartbeat(claim.id, self.worker_id)
            if status is None:
                cancel.lost_ownership = True
                cancel.event.set()
            elif status == RunStatus.CANCELLING:
                cancel.event.set()
            return status is not None

        def heartbeat_loop() -> None:
            while not done.wait(self.settings.heartbeat_interval_s):
                try:
                    beat()
                except Exception:  # transient DB error: keep going, recovery handles loss
                    log.exception("heartbeat failed for run %s", claim.id)

        progress_state = {"last": 0.0, "events": 0}
        limits = self.settings.limits

        def on_progress(e: ProgressEvent) -> None:
            now = time.monotonic()
            if now - progress_state["last"] < self.settings.progress_event_min_interval_s:
                return
            progress_state["last"] = now
            write_event = progress_state["events"] < limits.max_progress_events_per_run
            payload = json_safe(
                {
                    "iteration": e.iteration,
                    "evaluations": e.evaluations,
                    "elapsed_s": e.elapsed_s,
                    "best_objective": e.best_objective,
                    "current_objective": e.current_objective,
                    "has_feasible": e.has_feasible,
                    "message": e.message,
                    "attempt": claim.attempt,
                }
            )
            if self.queue.report_progress(claim.id, self.worker_id, payload, write_event):
                progress_state["events"] += int(write_event)

        thread = threading.Thread(target=heartbeat_loop, name=f"heartbeat-{claim.id}", daemon=True)
        try:
            if not beat():
                return None
            algorithm = self.algorithms.get(claim.algorithm_id)
            if algorithm is None:
                return self.queue.fail(
                    claim.id,
                    self.worker_id,
                    {
                        "code": "unknown_algorithm",
                        "message": f"{claim.algorithm_id!r} not available",
                    },
                )
            with session_scope(self.factory) as s:
                version = get_version(s, claim.scenario_version_id)
                scenario = load_version_scenario(version)
            thread.start()
            result = algorithm.run(
                AlgorithmInput(
                    scenario, claim.config, seed=claim.seed, progress=on_progress, cancel=cancel
                )
            )
        except Exception as exc:
            log.exception("run %s failed", claim.id)
            done.set()
            return self.queue.fail(
                claim.id,
                self.worker_id,
                {"code": "algorithm_error", "type": type(exc).__name__, "message": str(exc)[:500]},
            )
        finally:
            done.set()
            if thread.is_alive():
                thread.join()
        if cancel.lost_ownership:
            log.warning("run %s: ownership lost; result discarded", claim.id)
            return None
        final = self.queue.complete(claim.id, self.worker_id, result_to_row(result, self.software))
        log.info("run %s: %s (%s)", claim.id, final, result.termination_reason)
        return final


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true", help="run migrations first")
    parser.add_argument("--once", action="store_true", help="process at most one run, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = Settings.from_env()
    if not settings.database_url:
        raise SystemExit("TRAFIQON_DATABASE_URL is not set")
    if args.migrate:
        migrate(settings.database_url)
    factory = make_session_factory(make_engine(settings.database_url))
    queue = PostgresJobQueue(factory, stale_after_s=settings.stale_after_s)
    worker = Worker(factory, queue, settings)
    log.info("worker %s started", worker.worker_id)
    if args.once:
        worker.run_once()
        return
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    worker.run_forever(stop)
    log.info("worker %s stopped", worker.worker_id)


if __name__ == "__main__":
    main()

"""Scenario and immutable scenario-version persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from trafiqon.domain.models import Scenario
from trafiqon.domain.serialization import scenario_fingerprint, scenario_from_dict, scenario_to_dict
from trafiqon.persistence.models import (
    BenchmarkSuiteRow,
    RunRow,
    ScenarioRow,
    ScenarioVersionRow,
)


class ScenarioInUse(Exception):
    """A scenario cannot be deleted because runs or suites reference its versions."""


def create_scenario(
    session: Session, name: str, description: str, owner_id: str | None = None
) -> ScenarioRow:
    row = ScenarioRow(name=name, description=description, owner_id=owner_id)
    session.add(row)
    session.flush()
    return row


def add_version(
    session: Session, scenario: ScenarioRow, data: Scenario, note: str = ""
) -> ScenarioVersionRow:
    """Append a new immutable version and make it current. The scenario row is locked so
    concurrent version creation gets consecutive numbers."""
    session.execute(select(ScenarioRow.id).where(ScenarioRow.id == scenario.id).with_for_update())
    number = (
        session.scalar(
            select(func.coalesce(func.max(ScenarioVersionRow.version_number), 0)).where(
                ScenarioVersionRow.scenario_id == scenario.id
            )
        )
        + 1
    )
    stored = scenario_to_dict(data)
    stored["id"] = str(scenario.id)
    stored["name"] = scenario.name
    version = ScenarioVersionRow(
        scenario_id=scenario.id,
        version_number=number,
        data=stored,
        fingerprint=scenario_fingerprint(scenario_from_dict(stored)),
        synthetic=data.synthetic,
        node_count=len(data.graph.nodes),
        edge_count=len(data.graph.edges),
        customer_count=len(data.customers),
        vehicle_count=len(data.vehicles),
        note=note,
    )
    session.add(version)
    session.flush()
    scenario.current_version_id = version.id
    session.flush()
    return version


def get_scenario(session: Session, scenario_id: uuid.UUID) -> ScenarioRow | None:
    return session.get(ScenarioRow, scenario_id)


def list_scenarios(session: Session, limit: int, offset: int) -> tuple[list[ScenarioRow], int]:
    total = session.scalar(select(func.count()).select_from(ScenarioRow)) or 0
    rows = session.scalars(
        select(ScenarioRow)
        .order_by(ScenarioRow.created_at.desc(), ScenarioRow.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_version(session: Session, version_id: uuid.UUID) -> ScenarioVersionRow | None:
    return session.get(ScenarioVersionRow, version_id)


def get_version_by_number(
    session: Session, scenario_id: uuid.UUID, number: int
) -> ScenarioVersionRow | None:
    return session.scalar(
        select(ScenarioVersionRow).where(
            ScenarioVersionRow.scenario_id == scenario_id,
            ScenarioVersionRow.version_number == number,
        )
    )


def list_versions(session: Session, scenario_id: uuid.UUID) -> list[ScenarioVersionRow]:
    return list(
        session.scalars(
            select(ScenarioVersionRow)
            .where(ScenarioVersionRow.scenario_id == scenario_id)
            .order_by(ScenarioVersionRow.version_number)
        ).all()
    )


def update_metadata(session: Session, row: ScenarioRow, changes: dict[str, Any]) -> ScenarioRow:
    """Only name/description; graph data changes require a new version."""
    for key in ("name", "description"):
        if key in changes and changes[key] is not None:
            setattr(row, key, changes[key])
    session.flush()
    return row


def delete_scenario(session: Session, row: ScenarioRow) -> None:
    """Delete a scenario and its versions, unless any version is referenced by a run or suite."""
    version_ids = select(ScenarioVersionRow.id).where(ScenarioVersionRow.scenario_id == row.id)
    referenced = session.scalar(
        select(
            exists().where(RunRow.scenario_version_id.in_(version_ids))
            | exists().where(BenchmarkSuiteRow.scenario_version_id.in_(version_ids))
        )
    )
    if referenced:
        raise ScenarioInUse(str(row.id))
    row.current_version_id = None
    session.flush()
    session.delete(row)
    session.flush()


def load_version_scenario(version: ScenarioVersionRow) -> Scenario:
    return scenario_from_dict(version.data)

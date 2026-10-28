"""Core packages must not depend on web, database, queue or UI frameworks."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "trafiqon"
CORE = ["domain", "routing", "optimization", "simulation", "experiments", "fixtures"]
FORBIDDEN = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "celery",
    "redis",
    "pydantic_settings",
}
# Core may not import the outer layers either.
FORBIDDEN_INTERNAL = {"trafiqon.api", "trafiqon.persistence", "trafiqon.worker"}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


@pytest.mark.parametrize("package", CORE)
def test_core_has_no_framework_imports(package):
    files = list((SRC / package).rglob("*.py")) if (SRC / package).exists() else []
    for f in files:
        for name in _imports(f):
            assert name.split(".")[0] not in FORBIDDEN, f"{f.name} imports {name}"
            assert not any(name.startswith(p) for p in FORBIDDEN_INTERNAL), (
                f"{f.name} imports {name}"
            )

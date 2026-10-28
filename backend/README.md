# TRAFIQON backend

Python core (domain, routing) for the TRAFIQON workbench. Requires Python 3.12 and uv.

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Built-in scenarios (`trafiqon.fixtures.load_builtin`) are synthetic grids, not real road data.
See `../docs/mathematical_model.md` for the model, objective and evaluator.

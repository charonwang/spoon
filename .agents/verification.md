# verification

## Install (dev mode)

venv (recommended):
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

uv:
```powershell
uv venv --python ">=3.11"
uv pip install -e ".[dev]"
```

If pip is missing (Python 3.12+), bootstrap it first:
```powershell
python -m ensurepip --upgrade
```

py launcher (Windows; use any installed 3.11+ tag — the launcher needs an exact `-3.x`, not a range):
```powershell
py -3.11 -m pip install -e ".[dev]"
```

## Run tests

All:
```powershell
.venv\Scripts\python -m unittest discover -s tests -p "test_*.py"
```

Single file:
```powershell
.venv\Scripts\python -m unittest tests.test_runner_engine
```

Single case:
```powershell
.venv\Scripts\python -m unittest tests.test_runner_engine.RunnerEngineTests.test_brief_advances_to_plan_adoption
```

## Lint

```powershell
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff check . --fix
```

Config lives in `pyproject.toml` (`[tool.ruff]`): line length 120, rules `E/F/I/UP/B`, `templates.py` exempt from `E501`. CI runs `ruff check .` as a gate.

## Doc link check

```powershell
.venv\Scripts\python scripts/check_doc_links.py
```

## Run without installing

```powershell
$env:PYTHONPATH = "src"
python -m spoon init
```

## Pre-commit checklist

CI is the source of truth; local Windows passing is not green. The ubuntu matrix runs much faster and catches timing races that a slow Windows run hides.

- [ ] `ruff check .` is clean
- [ ] Full test suite passes
- [ ] New functionality has matching tests (`tests/test_<module>.py`)
- [ ] No architecture-paper jargon in comments or names
- [ ] All I/O goes through `io_util.py`
- [ ] JSON writes use `write_json_atomic`
- [ ] No hardcoded path strings; use `ProjectPaths`

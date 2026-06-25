# verification

## Install (dev mode)

Windows, py launcher:
```powershell
py -3.11 -m pip install -e ".[dev]"
```

uv:
```powershell
uv venv --python 3.11
uv pip install -e ".[dev]"
```

## Run tests

All:
```powershell
py -3.11 -m unittest discover -s tests -p "test_*.py"
```

Single file:
```powershell
py -3.11 -m unittest tests.test_runner_engine
```

Single case:
```powershell
py -3.11 -m unittest tests.test_runner_engine.TestAdvance.test_brief_phase
```

## Lint

```powershell
py -3.11 -m ruff check .
py -3.11 -m ruff check . --fix
```

Config lives in `pyproject.toml` (`[tool.ruff]`): line length 120, rules `E/F/I/UP/B`, `templates.py` exempt from `E501`. CI runs `ruff check .` as a gate.

## Doc link check

```powershell
py -3.11 scripts/check_doc_links.py
```

## Run without installing

```powershell
$env:PYTHONPATH = "src"
python -m spoon init
```

## Pre-commit checklist

- [ ] `ruff check .` is clean
- [ ] Full test suite passes
- [ ] New functionality has matching tests (`tests/test_<module>.py`)
- [ ] No architecture-paper jargon in comments or names
- [ ] All I/O goes through `io_util.py`
- [ ] JSON writes use `write_json_atomic`
- [ ] No hardcoded path strings; use `ProjectPaths`

from __future__ import annotations

from ..io_util import read_json, write_json_atomic
from ..paths import ProjectPaths
from .model import ImplementationRecord, RunState


def load_run_state(paths: ProjectPaths) -> RunState:
    if not paths.run_state.exists():
        return RunState.new("initial")
    data = read_json(paths.run_state)
    if not isinstance(data, dict):
        raise ValueError("run-state.json root must be an object")
    return RunState.from_dict(data)


def save_run_state(paths: ProjectPaths, state: RunState) -> None:
    write_json_atomic(paths.run_state, state.to_dict())


def load_implementation(paths: ProjectPaths) -> ImplementationRecord | None:
    if not paths.implementation.exists():
        return None
    data = read_json(paths.implementation)
    if not isinstance(data, dict):
        raise ValueError("implementation.json root must be an object")
    return ImplementationRecord.from_dict(data)


def save_implementation(paths: ProjectPaths, record: ImplementationRecord) -> None:
    write_json_atomic(paths.implementation, record.to_dict())

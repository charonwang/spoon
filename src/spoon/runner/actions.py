from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..io_util import read_json, read_text, write_json_atomic
from ..paths import ProjectPaths
from .events import append_event, load_events
from .model import (
    ActionKind,
    ActionStatus,
    ImplementationRecord,
    RunState,
    WorkflowAction,
    utc_now_iso,
)


class ActionsCorruptError(Exception):
    """Raised when actions.json exists but cannot be parsed."""


def action_id(
    run_id: str,
    phase: str,
    kind: str,
    prompt_path: str | None,
    output_path: str | None,
) -> str:
    payload = f"{run_id}\0{phase}\0{kind}\0{prompt_path or ''}\0{output_path or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def output_digest(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _save_actions(paths: ProjectPaths, actions: list[WorkflowAction]) -> None:
    write_json_atomic(paths.actions, [item.to_dict() for item in actions])


def _parse_actions(raw: object) -> list[WorkflowAction]:
    if not isinstance(raw, list):
        raise ActionsCorruptError("actions.json root must be an array")
    parsed: list[WorkflowAction] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ActionsCorruptError(
                f"actions.json entry at index {index} must be an object, got {type(item).__name__}"
            )
        parsed.append(WorkflowAction.from_dict(item))
    return parsed


def load_actions(paths: ProjectPaths) -> list[WorkflowAction]:
    if not paths.actions.exists():
        return []
    try:
        raw = read_json(paths.actions)
    except (json.JSONDecodeError, OSError) as exc:
        raise ActionsCorruptError(str(exc)) from exc
    try:
        return _parse_actions(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ActionsCorruptError(str(exc)) from exc


def _completion_record(events: list[dict[str, object]], action_id_value: str) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("type") != "action_completed":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if data.get("action_id") == action_id_value:
            return data
    return None


def _with_status_pending(action: WorkflowAction) -> WorkflowAction:
    return WorkflowAction(
        id=action.id,
        kind=action.kind,
        status=ActionStatus.PENDING,
        prompt_path=action.prompt_path,
        output_path=action.output_path,
        working_directory=action.working_directory,
        payload=action.payload,
        attempts=action.attempts,
        created_at=action.created_at,
        updated_at=utc_now_iso(),
    )


def _recover_status(
    action: WorkflowAction,
    events: list[dict[str, object]],
    repo: Path,
) -> WorkflowAction:
    record = _completion_record(events, action.id)
    if record is None:
        if action.status == ActionStatus.COMPLETED:
            return _with_status_pending(action)
        return action
    declared_output = action.output_path
    if not declared_output:
        return WorkflowAction(
            id=action.id,
            kind=action.kind,
            status=ActionStatus.COMPLETED,
            prompt_path=action.prompt_path,
            output_path=action.output_path,
            working_directory=action.working_directory,
            payload=action.payload,
            attempts=action.attempts,
            created_at=action.created_at,
            updated_at=utc_now_iso(),
        )
    output_path = repo / declared_output
    expected_digest = record.get("output_digest")
    if not output_path.is_file() or not read_text(output_path).strip():
        return _with_status_pending(action)
    if not isinstance(expected_digest, str):
        return _with_status_pending(action)
    if output_digest(output_path) != expected_digest:
        return _with_status_pending(action)
    return WorkflowAction(
        id=action.id,
        kind=action.kind,
        status=ActionStatus.COMPLETED,
        prompt_path=action.prompt_path,
        output_path=action.output_path,
        working_directory=action.working_directory,
        payload=action.payload,
        attempts=action.attempts,
        created_at=action.created_at,
        updated_at=utc_now_iso(),
    )


def enqueue_action(paths: ProjectPaths, action: WorkflowAction) -> WorkflowAction:
    actions = load_actions(paths) if paths.actions.exists() else []
    for index, existing in enumerate(actions):
        if existing.id == action.id:
            if (
                existing.kind == action.kind
                and existing.status == action.status
                and existing.payload == action.payload
            ):
                return existing
            now = utc_now_iso()
            updated = WorkflowAction(
                id=action.id,
                kind=action.kind,
                status=ActionStatus.PENDING,
                prompt_path=action.prompt_path,
                output_path=action.output_path,
                working_directory=action.working_directory,
                payload=action.payload,
                attempts=existing.attempts,
                created_at=existing.created_at,
                updated_at=now,
            )
            actions[index] = updated
            _save_actions(paths, actions)
            append_event(
                paths,
                "action_enqueued",
                {"action_id": updated.id, "kind": updated.kind.value, "phase": updated.payload.get("phase")},
            )
            return updated
    now = utc_now_iso()
    queued = WorkflowAction(
        id=action.id,
        kind=action.kind,
        status=ActionStatus.PENDING,
        prompt_path=action.prompt_path,
        output_path=action.output_path,
        working_directory=action.working_directory,
        payload=action.payload,
        attempts=action.attempts,
        created_at=action.created_at or now,
        updated_at=now,
    )
    actions.append(queued)
    _save_actions(paths, actions)
    append_event(
        paths,
        "action_enqueued",
        {"action_id": queued.id, "kind": queued.kind.value, "phase": queued.payload.get("phase")},
    )
    return queued


def is_implementation_action(action: WorkflowAction) -> bool:
    return action.kind in {ActionKind.CURSOR_AGENT_UI, ActionKind.MANUAL} and (
        action.payload.get("phase") == "implementation"
        or (action.output_path or "").endswith("implementation-summary.md")
    )


def _restore_bytes(path: Path, backup: bytes | None) -> None:
    if backup is not None:
        path.write_bytes(backup)
    elif path.exists():
        path.unlink(missing_ok=True)


def complete_action(
    paths: ProjectPaths,
    action_id_value: str,
    output_path: Path,
    *,
    implementation_record: ImplementationRecord | None = None,
) -> WorkflowAction:
    actions = load_actions(paths)
    target = next((item for item in actions if item.id == action_id_value), None)
    if target is None:
        raise ValueError(f"unknown action id: {action_id_value}")

    declared = target.output_path
    if declared is None:
        raise ValueError("action has no declared output path")
    resolved = output_path.resolve()
    expected = (paths.repo / declared).resolve()
    if resolved != expected:
        raise ValueError("output path does not match action contract")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    if not read_text(resolved).strip():
        raise ValueError("output file is empty")

    digest = output_digest(resolved)
    if target.status == ActionStatus.COMPLETED:
        record = _completion_record(load_events(paths), action_id_value)
        if record is None:
            raise ValueError("completed action missing event record")
        expected_digest = record.get("output_digest")
        if not isinstance(expected_digest, str) or expected_digest != digest:
            raise ValueError("output digest mismatch for already-completed action")
        return target

    now = utc_now_iso()
    completed = WorkflowAction(
        id=target.id,
        kind=target.kind,
        status=ActionStatus.COMPLETED,
        prompt_path=target.prompt_path,
        output_path=target.output_path,
        working_directory=target.working_directory,
        payload=target.payload,
        attempts=target.attempts + 1,
        created_at=target.created_at,
        updated_at=now,
    )
    updated = [completed if item.id == action_id_value else item for item in actions]

    actions_backup = paths.actions.read_bytes() if paths.actions.exists() else None
    implementation_backup = paths.implementation.read_bytes() if paths.implementation.exists() else None
    try:
        if implementation_record is not None:
            from .state_store import save_implementation

            save_implementation(paths, implementation_record)
        _save_actions(paths, updated)
        append_event(
            paths,
            "action_completed",
            {"action_id": completed.id, "output_path": declared, "output_digest": digest},
        )
    except Exception:
        _restore_bytes(paths.actions, actions_backup)
        _restore_bytes(paths.implementation, implementation_backup)
        raise
    return completed


def fail_action(paths: ProjectPaths, action_id_value: str, message: str) -> WorkflowAction:
    actions = load_actions(paths)
    target = next((item for item in actions if item.id == action_id_value), None)
    if target is None:
        raise ValueError(f"unknown action id: {action_id_value}")
    now = utc_now_iso()
    failed = WorkflowAction(
        id=target.id,
        kind=target.kind,
        status=ActionStatus.FAILED,
        prompt_path=target.prompt_path,
        output_path=target.output_path,
        working_directory=target.working_directory,
        payload=target.payload,
        attempts=target.attempts + 1,
        created_at=target.created_at,
        updated_at=now,
    )
    updated = [failed if item.id == action_id_value else item for item in actions]
    _save_actions(paths, updated)
    append_event(
        paths,
        "action_failed",
        {"action_id": failed.id, "message": message},
    )
    return failed


def rebuild_expected_actions(
    paths: ProjectPaths,
    state: RunState,
    expected: list[WorkflowAction],
) -> list[WorkflowAction]:
    events = load_events(paths)
    rebuilt: list[WorkflowAction] = []
    for action in expected:
        recovered = _recover_status(action, events, paths.repo)
        rebuilt.append(recovered)
    _save_actions(paths, rebuilt)
    append_event(
        paths,
        "action_queue_rebuilt",
        {"phase": state.phase.value, "count": len(rebuilt)},
    )
    return rebuilt


def ensure_actions(
    paths: ProjectPaths,
    state: RunState,
    expected: list[WorkflowAction],
) -> list[WorkflowAction]:
    if not paths.actions.exists():
        return rebuild_expected_actions(paths, state, expected)
    events = load_events(paths)
    existing = {item.id: item for item in load_actions(paths)}
    merged_map = dict(existing)
    for action in expected:
        current = existing.get(action.id, action)
        merged_map[action.id] = _recover_status(current, events, paths.repo)
    merged = list(merged_map.values())
    _save_actions(paths, merged)
    return merged

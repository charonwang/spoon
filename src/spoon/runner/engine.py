from __future__ import annotations

import uuid
from collections.abc import Mapping
from pathlib import Path

from ..adapters.base import Adapter, AdapterRequest, AdapterStatus
from ..adapters.manual import ManualAdapter
from ..commands.handoff_cmd import extract_accepted_for_handoff, generate_handoff
from ..commands.prompts_cmd import generate_prompts
from ..commands.snapshot_cmd import create_snapshot
from ..git_util import current_head_or_empty
from ..io_util import read_text, write_text
from ..paths import ProjectPaths, project_paths
from .actions import (
    ActionsCorruptError,
    action_id,
    complete_action,
    enqueue_action,
    ensure_actions,
    load_actions,
)
from .events import EventsCorruptError, append_event, load_events
from .gates import (
    code_review_gate,
    final_check_gate,
    implementation_gate,
    plan_review_gate,
)
from .model import (
    ActionKind,
    ActionStatus,
    RunnerResult,
    RunPhase,
    RunState,
    RunStatus,
    WorkflowAction,
    touch_state,
    utc_now_iso,
)
from .state_store import load_implementation, load_run_state, save_run_state

CURRENT = ".spoon/current"
_MANUAL_ADAPTER = ManualAdapter()
_EXIT_PRIORITY = {20: 3, 11: 2, 10: 1}


def rel(repo: Path, *parts: str) -> str:
    return Path(CURRENT, *parts).as_posix()


PLAN_REVIEW_SPECS = (
    (ActionKind.CLAUDE_REVIEW, "prompts/claude-plan-review.md", "reviews/claude-plan.md"),
    (ActionKind.CODEX_THREAD_MESSAGE, "prompts/codex-plan-review.md", "reviews/codex-plan.md"),
    (ActionKind.CLAUDE_REVIEW, "prompts/final-plan-review.md", "reviews/final-plan-review.md"),
)

CODE_REVIEW_SPECS = (
    (ActionKind.CLAUDE_REVIEW, "prompts/claude-code-review.md", "reviews/claude-code.md"),
    (ActionKind.CODEX_THREAD_MESSAGE, "prompts/codex-code-review.md", "reviews/codex-code.md"),
    (ActionKind.MANUAL, "handoff.md", "reviews/cursor-self-review.md"),
)

IMPLEMENTATION_SPEC = (
    ActionKind.CURSOR_AGENT_UI,
    "prompts/cursor-implement.md",
    "implementation-summary.md",
)

PLAN_ADOPTION_SPEC = (
    ActionKind.CURSOR_PLAN_UI,
    "prompts/cursor-plan.md",
    "plan.md",
)


def make_action(
    state: RunState,
    repo: Path,
    kind: ActionKind,
    prompt_suffix: str,
    output_suffix: str,
) -> WorkflowAction:
    prompt_path = rel(repo, prompt_suffix)
    output_path = rel(repo, output_suffix)
    now = utc_now_iso()
    return WorkflowAction(
        id=action_id(state.run_id, state.phase.value, kind.value, prompt_path, output_path),
        kind=kind,
        status=ActionStatus.PENDING,
        prompt_path=prompt_path,
        output_path=output_path,
        working_directory=str(repo.resolve()),
        payload={"phase": state.phase.value},
        attempts=0,
        created_at=now,
        updated_at=now,
    )


def ensure_implementation_base(paths: ProjectPaths) -> str:
    if paths.implementation_base.exists():
        existing = read_text(paths.implementation_base).strip()
        if existing:
            return existing
    base_sha = current_head_or_empty(paths.repo)
    write_text(paths.implementation_base, base_sha + "\n")
    append_event(paths, "implementation_base_recorded", {"base_sha": base_sha})
    return base_sha


def read_implementation_base_for_action(paths: ProjectPaths) -> str:
    if paths.implementation_base.exists():
        existing = read_text(paths.implementation_base).strip()
        if existing:
            return existing
    # Recovery fallback: if local .spoon state was deleted, keep the action usable.
    # Earlier checkpoint commits may not be included in later base..HEAD snapshots.
    return current_head_or_empty(paths.repo)


def expected_actions(state: RunState, repo: Path) -> list[WorkflowAction]:
    if state.phase == RunPhase.PLAN_ADOPTION:
        kind, prompt, output = PLAN_ADOPTION_SPEC
        return [make_action(state, repo, kind, prompt, output)]
    if state.phase == RunPhase.PLAN_REVIEW:
        return [
            make_action(state, repo, kind, prompt, output)
            for kind, prompt, output in PLAN_REVIEW_SPECS
        ]
    if state.phase == RunPhase.IMPLEMENTATION:
        kind, prompt, output = IMPLEMENTATION_SPEC
        action = make_action(state, repo, kind, prompt, output)
        paths = project_paths(repo)
        base_sha = read_implementation_base_for_action(paths)
        return [
            WorkflowAction(
                id=action.id,
                kind=action.kind,
                status=action.status,
                prompt_path=action.prompt_path,
                output_path=action.output_path,
                working_directory=action.working_directory,
                payload={**action.payload, "implementation_base_sha": base_sha},
                attempts=action.attempts,
                created_at=action.created_at,
                updated_at=action.updated_at,
            )
        ]
    if state.phase == RunPhase.CODE_REVIEW:
        return [
            make_action(state, repo, kind, prompt, output)
            for kind, prompt, output in CODE_REVIEW_SPECS
        ]
    return []


def plan_has_content(paths: ProjectPaths) -> bool:
    if not paths.plan.is_file():
        return False
    text = read_text(paths.plan).strip()
    if not text:
        return False
    body = text
    if body.startswith("<!-- spoon adopted-plan"):
        end = body.find("-->")
        if end != -1:
            body = body[end + 3 :].strip()
    return bool(body)


def pending_actions(actions: list[WorkflowAction]) -> list[WorkflowAction]:
    return [item for item in actions if item.status == ActionStatus.PENDING]


def failed_actions_for_expected(
    actions: list[WorkflowAction],
    expected: list[WorkflowAction],
) -> list[WorkflowAction]:
    expected_ids = {item.id for item in expected}
    relevant = [item for item in actions if item.id in expected_ids]
    completed_ids = {item.id for item in relevant if item.status == ActionStatus.COMPLETED}
    return [
        item
        for item in relevant
        if item.status == ActionStatus.FAILED and item.id not in completed_ids
    ]


def _prefer_exit(current: int | None, new: int | None) -> int | None:
    if new is None:
        return current
    if current is None:
        return new
    if _EXIT_PRIORITY.get(new, 0) >= _EXIT_PRIORITY.get(current, 0):
        return new
    return current


def _phase_actions_blocked(
    paths: ProjectPaths,
    state: RunState,
    expected: list[WorkflowAction],
    actions: list[WorkflowAction],
) -> RunnerResult | None:
    failed = failed_actions_for_expected(actions, expected)
    if not failed:
        return None
    if pending_actions([item for item in actions if item.id in {e.id for e in expected}]):
        return None
    message = "; ".join(f"{item.id} failed" for item in failed)
    updated = touch_state(
        state,
        status=RunStatus.FAILED,
        pending_decision=f"Workflow actions failed: {message}",
        last_error=message,
    )
    save_run_state(paths, updated)
    append_event(paths, "runner_failed", {"message": message})
    return RunnerResult(21, updated, tuple(failed))


def save_phase(paths: ProjectPaths, state: RunState, phase: RunPhase, status: RunStatus) -> RunState:
    updated = touch_state(state, phase=phase, status=status, pending_decision=None, last_error=None)
    save_run_state(paths, updated)
    append_event(paths, "phase_changed", {"phase": phase.value, "status": status.value})
    return updated


def has_fresh_snapshot(paths: ProjectPaths, completed_at: str) -> bool:
    for event in load_events(paths):
        if event.get("type") != "snapshot_created":
            continue
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str) and timestamp > completed_at:
            return True
    return False


def record_snapshot(paths: ProjectPaths) -> None:
    create_snapshot(paths.repo, test_cmd=None, dependency_cmd=None)
    append_event(paths, "snapshot_created", {})


def adapter_for(kind: ActionKind, adapters: Mapping[str, Adapter]) -> Adapter | None:
    return adapters.get(kind.value)


def process_adapter_action(
    paths: ProjectPaths,
    action: WorkflowAction,
    adapters: Mapping[str, Adapter],
) -> tuple[int | None, list[WorkflowAction], str | None]:
    manual = _MANUAL_ADAPTER
    request = AdapterRequest(
        prompt_path=action.prompt_path or "",
        output_path=action.output_path or "",
        working_directory=action.working_directory,
        action_id=action.id,
    )
    adapter = adapter_for(action.kind, adapters)
    if adapter is None:
        result = manual.execute(request)
        if result.action is not None:
            fallback = WorkflowAction(
                id=action.id,
                kind=ActionKind.MANUAL,
                status=ActionStatus.PENDING,
                prompt_path=action.prompt_path,
                output_path=action.output_path,
                working_directory=action.working_directory,
                payload=result.action.payload,
                attempts=action.attempts,
                created_at=action.created_at,
                updated_at=utc_now_iso(),
            )
            enqueue_action(paths, fallback)
            return 20, [fallback], None
        return 20, [], None

    result = adapter.execute(request)
    if result.status == AdapterStatus.SUCCESS:
        output = paths.repo / (action.output_path or "")
        if output.is_file() and read_text(output).strip():
            complete_action(paths, action.id, output)
        return None, [], None
    if result.status == AdapterStatus.NEEDS_USER:
        return 10, [], result.message
    if result.status in {AdapterStatus.UNAVAILABLE, AdapterStatus.FAILED}:
        manual_result = manual.execute(request)
        if manual_result.action is not None:
            fallback = WorkflowAction(
                id=action.id,
                kind=ActionKind.MANUAL,
                status=ActionStatus.PENDING,
                prompt_path=action.prompt_path,
                output_path=action.output_path,
                working_directory=action.working_directory,
                payload=manual_result.action.payload,
                attempts=action.attempts,
                created_at=action.created_at,
                updated_at=utc_now_iso(),
            )
            enqueue_action(paths, fallback)
            return 20, [fallback], None
        return 20, [], None
    if result.status == AdapterStatus.NEEDS_HOST:
        host_action = result.action or action
        enqueue_action(paths, host_action)
        return 11, [host_action], None
    return None, [], None


def handle_review_phase(
    paths: ProjectPaths,
    state: RunState,
    adapters: Mapping[str, Adapter],
    next_phase: RunPhase,
) -> RunnerResult:
    expected = expected_actions(state, paths.repo)
    actions = ensure_actions(paths, state, expected)
    blocked = _phase_actions_blocked(paths, state, expected, actions)
    if blocked is not None:
        return blocked

    exit_override: int | None = None
    pending_decision: str | None = None

    for action in list(actions):
        if action.status != ActionStatus.PENDING:
            continue
        if action.kind == ActionKind.CLAUDE_REVIEW:
            code, items, decision = process_adapter_action(paths, action, adapters)
            exit_override = _prefer_exit(exit_override, code)
            if decision:
                pending_decision = decision
            if code == 20 or code == 10:
                break
        elif action.kind in {
            ActionKind.CODEX_THREAD_MESSAGE,
            ActionKind.MANUAL,
        }:
            if exit_override == 20:
                continue
            enqueue_action(paths, action)
            exit_override = _prefer_exit(exit_override, 11)

    actions = load_actions(paths)
    blocked = _phase_actions_blocked(paths, state, expected, actions)
    if blocked is not None:
        return blocked

    if exit_override == 10:
        updated = touch_state(
            state,
            status=RunStatus.NEEDS_USER,
            pending_decision=pending_decision or "Adapter requires user decision.",
        )
        save_run_state(paths, updated)
        return RunnerResult(10, updated, tuple())

    pending = [
        item
        for item in pending_actions(actions)
        if item.id in {expected_action.id for expected_action in expected}
    ]
    if pending:
        updated = touch_state(state, status=RunStatus.NEEDS_HOST)
        save_run_state(paths, updated)
        code = exit_override if exit_override is not None else 11
        return RunnerResult(code, updated, tuple(pending))

    updated = save_phase(paths, state, next_phase, RunStatus.READY)
    return RunnerResult(0, updated, tuple())


def implementation_preconditions(paths: ProjectPaths) -> tuple[bool, str]:
    record = load_implementation(paths)
    if record is None:
        return False, "implementation.json is missing"
    if record.status != "reported_complete":
        return False, "implementation is not reported complete"
    actions = load_actions(paths)
    impl_action = next((item for item in actions if item.id == record.action_id), None)
    if impl_action is None or impl_action.status != ActionStatus.COMPLETED:
        return False, "implementation action is not completed"
    if not has_fresh_snapshot(paths, record.completed_at):
        return False, "post-implementation snapshot is missing"
    return True, ""


def _advance_one(
    paths: ProjectPaths,
    state: RunState,
    adapters: Mapping[str, Adapter],
) -> RunnerResult:
    phase = state.phase

    if phase == RunPhase.BRIEF:
        updated = save_phase(paths, state, RunPhase.PLAN_ADOPTION, RunStatus.READY)
        return RunnerResult(0, updated, tuple())

    if phase == RunPhase.PLAN_ADOPTION:
        if plan_has_content(paths):
            generate_prompts(paths.repo)
            updated = save_phase(paths, state, RunPhase.PLAN_REVIEW, RunStatus.READY)
            return RunnerResult(0, updated, tuple())
        action = make_action(state, paths.repo, *PLAN_ADOPTION_SPEC)
        queued = enqueue_action(paths, action)
        updated = touch_state(state, status=RunStatus.NEEDS_HOST)
        save_run_state(paths, updated)
        return RunnerResult(11, updated, (queued,))

    if phase == RunPhase.PLAN_REVIEW:
        generate_prompts(paths.repo)
        return handle_review_phase(paths, state, adapters, RunPhase.PLAN_DECISION)

    if phase == RunPhase.PLAN_DECISION:
        gate = plan_review_gate(paths)
        if gate.needs_user:
            updated = touch_state(
                state,
                status=RunStatus.NEEDS_USER,
                pending_decision=gate.reason,
            )
            save_run_state(paths, updated)
            return RunnerResult(10, updated, tuple())
        if not gate.ready:
            updated = touch_state(state, status=RunStatus.READY)
            save_run_state(paths, updated)
            return RunnerResult(0, updated, tuple())
        accepted = extract_accepted_for_handoff(read_text(paths.review_board))
        if not accepted or accepted == "_No approved changes yet._":
            updated = touch_state(
                state,
                status=RunStatus.NEEDS_USER,
                pending_decision="No approved handoff items on the review board.",
            )
            save_run_state(paths, updated)
            return RunnerResult(10, updated, tuple())
        ensure_implementation_base(paths)
        generate_handoff(paths.repo)
        updated = save_phase(paths, state, RunPhase.IMPLEMENTATION, RunStatus.READY)
        return RunnerResult(0, updated, tuple())

    if phase == RunPhase.IMPLEMENTATION:
        gate = implementation_gate(paths)
        if not gate.ready:
            updated = touch_state(
                state,
                status=RunStatus.NEEDS_USER,
                pending_decision=gate.reason,
            )
            save_run_state(paths, updated)
            return RunnerResult(10, updated, tuple())
        expected = expected_actions(state, paths.repo)
        actions = ensure_actions(paths, state, expected)
        impl_action = expected[0] if expected else None
        if impl_action is not None:
            current = next((item for item in actions if item.id == impl_action.id), impl_action)
            if current.status == ActionStatus.PENDING:
                queued = enqueue_action(paths, current)
                updated = touch_state(state, status=RunStatus.NEEDS_HOST)
                save_run_state(paths, updated)
                return RunnerResult(11, updated, (queued,))
        record = load_implementation(paths)
        if record is None:
            updated = touch_state(state, status=RunStatus.NEEDS_HOST)
            save_run_state(paths, updated)
            return RunnerResult(11, updated, tuple(pending_actions(actions)))
        if not has_fresh_snapshot(paths, record.completed_at):
            record_snapshot(paths)
        ready, reason = implementation_preconditions(paths)
        if not ready:
            updated = touch_state(state, status=RunStatus.READY, pending_decision=reason)
            save_run_state(paths, updated)
            return RunnerResult(0, updated, tuple())
        generate_prompts(paths.repo)
        updated = save_phase(paths, state, RunPhase.CODE_REVIEW, RunStatus.READY)
        return RunnerResult(0, updated, tuple())

    if phase == RunPhase.CODE_REVIEW:
        ready, reason = implementation_preconditions(paths)
        if not ready:
            if reason == "post-implementation snapshot is missing":
                record_snapshot(paths)
            updated = touch_state(state, status=RunStatus.READY, pending_decision=reason)
            save_run_state(paths, updated)
            return RunnerResult(0, updated, tuple())
        generate_prompts(paths.repo)
        return handle_review_phase(paths, state, adapters, RunPhase.CODE_DECISION)

    if phase == RunPhase.CODE_DECISION:
        gate = code_review_gate(paths)
        if gate.needs_user:
            updated = touch_state(
                state,
                status=RunStatus.NEEDS_USER,
                pending_decision=gate.reason,
            )
            save_run_state(paths, updated)
            return RunnerResult(10, updated, tuple())
        updated = save_phase(paths, state, RunPhase.FINAL_CHECK, RunStatus.READY)
        return RunnerResult(0, updated, tuple())

    if phase == RunPhase.FINAL_CHECK:
        gate = final_check_gate(paths)
        if gate.needs_user:
            updated = touch_state(
                state,
                status=RunStatus.NEEDS_USER,
                pending_decision=gate.reason,
            )
            save_run_state(paths, updated)
            return RunnerResult(10, updated, tuple())
        updated = save_phase(paths, state, RunPhase.ARCHIVE_READY, RunStatus.COMPLETE)
        return RunnerResult(0, updated, tuple())

    if phase == RunPhase.ARCHIVE_READY:
        updated = touch_state(state, status=RunStatus.COMPLETE)
        save_run_state(paths, updated)
        return RunnerResult(0, updated, tuple())

    updated = touch_state(state, status=RunStatus.FAILED, last_error=f"unknown phase: {phase}")
    save_run_state(paths, updated)
    return RunnerResult(21, updated, tuple())


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def advance(repo: Path, adapters: Mapping[str, Adapter] | None = None) -> RunnerResult:
    paths = project_paths(repo)
    adapter_map = adapters or {}
    state = load_run_state(paths)
    if state.run_id == "initial":
        state = RunState.new(new_run_id())
        save_run_state(paths, state)
    try:
        if paths.actions.exists():
            load_actions(paths)
    except ActionsCorruptError as exc:
        failed = touch_state(state, status=RunStatus.FAILED, last_error=str(exc))
        save_run_state(paths, failed)
        append_event(paths, "runner_failed", {"message": str(exc)})
        return RunnerResult(21, failed, tuple())
    try:
        if paths.events.exists():
            load_events(paths)
    except EventsCorruptError as exc:
        failed = touch_state(state, status=RunStatus.FAILED, last_error=str(exc))
        save_run_state(paths, failed)
        append_event(paths, "runner_failed", {"message": str(exc)})
        return RunnerResult(21, failed, tuple())
    try:
        return _advance_one(paths, state, adapter_map)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        failed = touch_state(state, status=RunStatus.FAILED, last_error=str(exc))
        save_run_state(paths, failed)
        append_event(paths, "runner_failed", {"message": str(exc)})
        return RunnerResult(21, failed, tuple())

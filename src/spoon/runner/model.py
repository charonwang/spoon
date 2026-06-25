from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal


class RunPhase(StrEnum):
    BRIEF = "brief"
    PLAN_ADOPTION = "plan_adoption"
    PLAN_REVIEW = "plan_review"
    PLAN_DECISION = "plan_decision"
    IMPLEMENTATION = "implementation"
    CODE_REVIEW = "code_review"
    CODE_DECISION = "code_decision"
    FINAL_CHECK = "final_check"
    ARCHIVE_READY = "archive_ready"


class RunStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    NEEDS_HOST = "needs_host"
    NEEDS_USER = "needs_user"
    FAILED = "failed"
    COMPLETE = "complete"


class ActionKind(StrEnum):
    CLAUDE_REVIEW = "claude_review"
    CODEX_THREAD_MESSAGE = "codex_thread_message"
    CURSOR_PLAN_UI = "cursor_plan_ui"
    CURSOR_AGENT_UI = "cursor_agent_ui"
    MANUAL = "manual"


class ActionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class RunState:
    schema_version: int
    run_id: str
    phase: RunPhase
    status: RunStatus
    pending_decision: str | None
    last_error: str | None
    updated_at: str

    @classmethod
    def new(cls, run_id: str) -> RunState:
        now = utc_now_iso()
        return cls(
            schema_version=1,
            run_id=run_id,
            phase=RunPhase.BRIEF,
            status=RunStatus.READY,
            pending_decision=None,
            last_error=None,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "phase": self.phase.value,
            "status": self.status.value,
            "pending_decision": self.pending_decision,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> RunState:
        for key in ("schema_version", "run_id", "phase", "status", "updated_at"):
            if key not in value:
                raise ValueError(f"missing {key}")
        return cls(
            schema_version=int(value["schema_version"]),
            run_id=str(value["run_id"]),
            phase=RunPhase(str(value["phase"])),
            status=RunStatus(str(value["status"])),
            pending_decision=(
                None if value.get("pending_decision") is None else str(value["pending_decision"])
            ),
            last_error=None if value.get("last_error") is None else str(value["last_error"]),
            updated_at=str(value["updated_at"]),
        )


@dataclass(frozen=True)
class WorkflowAction:
    id: str
    kind: ActionKind
    status: ActionStatus
    prompt_path: str | None
    output_path: str | None
    working_directory: str
    payload: dict[str, object]
    attempts: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "status": self.status.value,
            "prompt_path": self.prompt_path,
            "output_path": self.output_path,
            "working_directory": self.working_directory,
            "payload": self.payload,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> WorkflowAction:
        for key in ("id", "kind", "status", "working_directory", "attempts", "created_at", "updated_at"):
            if key not in value:
                raise ValueError(f"missing {key}")
        return cls(
            id=str(value["id"]),
            kind=ActionKind(str(value["kind"])),
            status=ActionStatus(str(value["status"])),
            prompt_path=(
                None if value.get("prompt_path") is None else str(value["prompt_path"])
            ),
            output_path=(
                None if value.get("output_path") is None else str(value["output_path"])
            ),
            working_directory=str(value["working_directory"]),
            payload=dict(value.get("payload") or {}),
            attempts=int(value["attempts"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
        )


@dataclass(frozen=True)
class ImplementationRecord:
    schema_version: int
    status: Literal["reported_complete"]
    action_id: str
    completed_at: str
    summary_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "action_id": self.action_id,
            "completed_at": self.completed_at,
            "summary_path": self.summary_path,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> ImplementationRecord:
        for key in ("schema_version", "status", "action_id", "completed_at", "summary_path"):
            if key not in value:
                raise ValueError(f"missing {key}")
        status = str(value["status"])
        if status != "reported_complete":
            raise ValueError(f"unexpected implementation status: {status}")
        return cls(
            schema_version=int(value["schema_version"]),
            status="reported_complete",
            action_id=str(value["action_id"]),
            completed_at=str(value["completed_at"]),
            summary_path=str(value["summary_path"]),
        )


@dataclass(frozen=True)
class RunnerResult:
    exit_code: int
    state: RunState
    actions: tuple[WorkflowAction, ...]


def touch_state(state: RunState, **changes: object) -> RunState:
    updates = dict(changes)
    updates["updated_at"] = utc_now_iso()
    return replace(state, **updates)

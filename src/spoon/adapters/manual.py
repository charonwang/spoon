from __future__ import annotations

from ..runner.model import ActionKind, ActionStatus, WorkflowAction, utc_now_iso
from .base import AdapterRequest, AdapterResult, AdapterStatus


class ManualAdapter:
    def execute(self, request: AdapterRequest) -> AdapterResult:
        complete_cmd = (
            f"spoon action complete --id {request.action_id} "
            f"--output {request.output_path}"
        )
        fail_cmd = f'spoon action fail --id {request.action_id} --message "<reason>"'
        instructions = (
            f"Read prompt: {request.prompt_path}\n"
            f"Write output to: {request.output_path}\n"
            f"Working directory: {request.working_directory}\n"
            f"On success run:\n{complete_cmd}\n"
            f"If unsafe to continue run:\n{fail_cmd}"
        )
        now = utc_now_iso()
        action = WorkflowAction(
            id=request.action_id,
            kind=ActionKind.MANUAL,
            status=ActionStatus.PENDING,
            prompt_path=request.prompt_path,
            output_path=request.output_path,
            working_directory=request.working_directory,
            payload={"instructions": instructions},
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        return AdapterResult(
            status=AdapterStatus.NEEDS_HOST,
            message="Manual action required.",
            action=action,
        )

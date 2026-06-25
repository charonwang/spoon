from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ..runner.model import WorkflowAction


class AdapterStatus(StrEnum):
    SUCCESS = "success"
    NEEDS_HOST = "needs_host"
    NEEDS_USER = "needs_user"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class AdapterRequest:
    action_id: str
    prompt_path: str
    output_path: str
    working_directory: str
    timeout_seconds: int = 300


@dataclass(frozen=True)
class AdapterResult:
    status: AdapterStatus
    message: str
    action: WorkflowAction | None = None


class Adapter(Protocol):
    def execute(self, request: AdapterRequest) -> AdapterResult: ...

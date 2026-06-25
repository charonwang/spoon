from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..io_util import read_text, write_text
from ..review_parser import classify_review_text
from .base import AdapterRequest, AdapterResult, AdapterStatus

FORBIDDEN_FLAGS = (
    "--yolo",
    "--dangerously-skip-permissions",
    "--allow-dangerously-skip-permissions",
)

REVIEW_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["approved", "changes_requested", "blocked"],
        },
        "summary": {"type": "string"},
        "findings_markdown": {"type": "string"},
    },
    "required": ["verdict", "summary", "findings_markdown"],
    "additionalProperties": False,
}

JSON_PROMPT_SUFFIX = """

Respond with JSON only using this shape:
{
  "verdict": "approved|changes_requested|blocked",
  "summary": "short summary",
  "findings_markdown": "markdown findings body"
}
"""

AUTH_FAILURE_RE = re.compile(
    r"authentication|not logged in|login required|invalid api key|api key",
    re.IGNORECASE,
)

_EMPTY_FINDINGS_BODY = "### Optional\n\n- _None._\n"


@dataclass(frozen=True)
class ClaudeCapabilities:
    json_output: bool
    json_schema: bool


def _detect_claude_capabilities(command: str) -> ClaudeCapabilities | None:
    try:
        proc = subprocess.run(
            [command, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None
    help_text = proc.stdout + proc.stderr
    return ClaudeCapabilities(
        json_output="--output-format" in help_text,
        json_schema="--json-schema" in help_text,
    )


_REVIEW_WRAPPER_KEYS = frozenset({"structured_output", "result", "content"})


def _validate_review_payload(data: object) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ValueError("review payload must be an object")
    allowed = frozenset({"verdict", "summary", "findings_markdown"})
    extra = set(data.keys()) - allowed - _REVIEW_WRAPPER_KEYS
    if extra:
        raise ValueError(f"unexpected review fields: {sorted(extra)}")
    for key in allowed:
        if key not in data:
            raise ValueError(f"missing {key}")
    verdict = data["verdict"]
    summary = data["summary"]
    findings_markdown = data["findings_markdown"]
    if not isinstance(verdict, str):
        raise ValueError("verdict must be a string")
    if verdict not in {"approved", "changes_requested", "blocked"}:
        raise ValueError(f"invalid verdict: {verdict}")
    if not isinstance(summary, str):
        raise ValueError("summary must be a string")
    if not isinstance(findings_markdown, str):
        raise ValueError("findings_markdown must be a string")
    return {
        "verdict": verdict,
        "summary": summary,
        "findings_markdown": findings_markdown,
    }


def _parse_json_text(text: str) -> dict[str, str]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty claude output")
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise ValueError("review payload must be an object")
    for key in ("structured_output", "result", "content"):
        if key not in data:
            continue
        candidate: object = data[key]
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        if isinstance(candidate, dict):
            return _validate_review_payload(candidate)
    if {"verdict", "summary", "findings_markdown"}.issubset(data.keys()):
        return _validate_review_payload(data)
    raise ValueError("unrecognized claude json output")


def _findings_body(findings_markdown: str) -> str:
    findings = findings_markdown.strip()
    if not findings or findings == "_None._":
        return _EMPTY_FINDINGS_BODY
    return findings.rstrip() + "\n"


def render_claude_review(payload: dict[str, str]) -> str:
    return (
        "# Claude Review\n\n"
        f"## Verdict\n\n{payload['verdict']}\n\n"
        f"## Summary\n\n{payload['summary']}\n\n"
        f"## Findings\n\n{_findings_body(payload['findings_markdown'])}"
    )


def _write_review_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
    try:
        write_text(temp_path, text)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


class ClaudeCliAdapter:
    def __init__(
        self,
        command: str = "claude",
        model: str | None = None,
        max_budget_usd: Decimal | None = None,
    ) -> None:
        self.command = command
        self.model = model
        self.max_budget_usd = max_budget_usd
        self._capabilities: ClaudeCapabilities | None | bool = False

    def _capabilities_for(self) -> ClaudeCapabilities | None:
        if self._capabilities is False:
            self._capabilities = _detect_claude_capabilities(self.command)
        if isinstance(self._capabilities, ClaudeCapabilities):
            return self._capabilities
        return None

    def execute(self, request: AdapterRequest) -> AdapterResult:
        repo = Path(request.working_directory)
        prompt_path = repo / request.prompt_path
        output_path = repo / request.output_path
        if not prompt_path.is_file():
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"prompt file not found: {request.prompt_path}",
            )

        capabilities = self._capabilities_for()
        if capabilities is None:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"claude command not found: {self.command}",
            )
        if not capabilities.json_output:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message="claude does not support structured --output-format json",
            )

        prompt_text = read_text(prompt_path)
        use_schema = capabilities.json_schema
        if not use_schema:
            prompt_text = prompt_text.rstrip() + JSON_PROMPT_SUFFIX

        cmd: list[str] = [self.command, "-p", "--output-format", "json"]
        if use_schema:
            cmd.extend(["--json-schema", json.dumps(REVIEW_JSON_SCHEMA)])
        if self.model:
            cmd.extend(["--model", self.model])
        if self.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", format(self.max_budget_usd, "f")])
        cmd.extend(["--add-dir", str(repo.resolve())])
        cmd.append(prompt_text)

        try:
            proc = subprocess.run(
                cmd,
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"claude command not found: {self.command}",
            )
        except subprocess.TimeoutExpired:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"claude command timed out after {request.timeout_seconds}s",
            )

        auth_text = f"{proc.stderr}\n{proc.stdout}"
        if proc.returncode != 0:
            if AUTH_FAILURE_RE.search(auth_text):
                return AdapterResult(
                    status=AdapterStatus.UNAVAILABLE,
                    message="claude authentication failed",
                )
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"claude exited with code {proc.returncode}",
            )

        try:
            payload = _parse_json_text(proc.stdout)
            rendered = render_claude_review(payload)
            groups = classify_review_text(output_path.name, rendered)
            if any("[PARSER WARNING]" in item for item in groups["Needs Triage"]):
                raise ValueError("rendered review would trigger parser warnings")
        except (json.JSONDecodeError, ValueError) as exc:
            if output_path.is_file() and read_text(output_path).strip():
                return AdapterResult(
                    status=AdapterStatus.FAILED,
                    message=f"invalid claude review json: {exc}",
                )
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"invalid claude review json: {exc}",
            )

        if output_path.is_file() and read_text(output_path).strip():
            existing = read_text(output_path)
            existing_groups = classify_review_text(output_path.name, existing)
            has_existing = not any(
                "[PARSER WARNING]" in item for item in existing_groups["Needs Triage"]
            )
            if has_existing:
                return AdapterResult(
                    status=AdapterStatus.FAILED,
                    message="refusing to overwrite existing valid review file",
                )

        _write_review_atomic(output_path, rendered)
        return AdapterResult(status=AdapterStatus.SUCCESS, message="review written")

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..io_util import read_text, write_text
from ..paths import project_paths
from ..review_parser import classify_review_text
from ..spoon_config import TerminalConfig
from .base import AdapterRequest, AdapterResult, AdapterStatus
from .claude_sessions import ensure_claude_session_id
from .command_util import resolve_executable
from .terminal_launch import (
    launch_external_terminal,
    resolve_terminal,
    wait_for_exit_file,
    wait_for_nonempty_file,
    write_visible_job,
)

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
    stream_json: bool = False
    partial_messages: bool = False


def _detect_claude_capabilities(command: str) -> ClaudeCapabilities | None:
    try:
        proc = subprocess.run(
            [command, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
        stream_json="stream-json" in help_text,
        partial_messages="--include-partial-messages" in help_text,
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


def _parse_stream_json_lines(lines: Iterable[str]) -> dict[str, str]:
    last_payload: dict[str, str] | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            last_payload = _parse_json_text(stripped)
        except (ValueError, json.JSONDecodeError):
            continue
    if last_payload is None:
        raise ValueError("no review payload in stream-json output")
    return last_payload


def _unwrap_stream_event(data: dict) -> dict:
    if data.get("type") == "stream_event":
        nested = data.get("event")
        if isinstance(nested, dict):
            return nested
    return data


def _humanize_stream_json_line(line: str) -> str | None:
    """Extract human-readable fragments from Claude stream-json lines.

    Visible mode must not dump raw JSON; only thinking/text deltas (and a few
    status cues) are shown. Status cues stay English; task prose language is
    controlled by prompt Task language, not these labels.
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped + "\n"
    if not isinstance(raw, dict):
        return None

    data = _unwrap_stream_event(raw)
    event_type = data.get("type")

    if event_type == "content_block_delta":
        delta = data.get("delta")
        if not isinstance(delta, dict):
            return None
        delta_type = delta.get("type")
        if delta_type == "thinking_delta":
            thinking = delta.get("thinking")
            return thinking if isinstance(thinking, str) else None
        if delta_type == "text_delta":
            text = delta.get("text")
            return text if isinstance(text, str) else None
        return None

    if event_type == "content_block_start":
        block = data.get("content_block")
        if isinstance(block, dict) and block.get("type") == "thinking":
            return "\nspoon: Claude thinking...\n"
        if isinstance(block, dict) and block.get("type") == "text":
            return "\nspoon: Claude writing...\n"
        return None

    if event_type == "content_block_stop":
        return "\n"

    if event_type == "message_start":
        return "spoon: Claude session started\n"

    if event_type == "message_stop":
        return "spoon: Claude session finished\n"

    if event_type == "system" and data.get("subtype") == "thinking_tokens":
        return None

    if {"verdict", "summary", "findings_markdown"}.issubset(data.keys()):
        return "spoon: Claude review payload received\n"
    if "result" in data or "structured_output" in data:
        return "spoon: Claude review payload received\n"

    return None


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
        conversation_title: str | None = None,
        max_budget_usd: Decimal | None = None,
        visible: bool = False,
        terminal: TerminalConfig | None = None,
        ui: str = "interactive",
        session_key: str | None = None,
    ) -> None:
        self.command = command
        self.model = model
        self.conversation_title = conversation_title
        self.max_budget_usd = max_budget_usd
        self.visible = visible
        self.terminal = terminal or TerminalConfig()
        self.ui = ui if ui in {"interactive", "print"} else "interactive"
        self.session_key = session_key
        self._capabilities: ClaudeCapabilities | None | bool = False

    def _capabilities_for(self) -> ClaudeCapabilities | None:
        if self._capabilities is False:
            self._capabilities = _detect_claude_capabilities(self.command)
        if isinstance(self._capabilities, ClaudeCapabilities):
            return self._capabilities
        return None

    def _build_interactive_cmd(
        self,
        repo: Path,
        *,
        session_id: str,
        created_new: bool,
        prompt_text: str,
    ) -> list[str]:
        cmd: list[str] = [resolve_executable(self.command)]
        if created_new:
            cmd.extend(["--session-id", session_id])
        else:
            cmd.extend(["--resume", session_id])
        if self.conversation_title:
            cmd.extend(["--name", self.conversation_title])
        if self.model:
            cmd.extend(["--model", self.model])
        # Allow writing review files without interactive permission prompts.
        cmd.extend(["--permission-mode", "acceptEdits"])
        cmd.extend(["--add-dir", str(repo.resolve())])
        cmd.append(prompt_text)
        return cmd

    def _interactive_prompt(
        self,
        request: AdapterRequest,
        *,
        created_new: bool,
    ) -> str:
        continuity = (
            "This is a new Spoon review session."
            if created_new
            else "Resume this Spoon review session; prior turns in this run are context."
        )
        return (
            f"{continuity} Read the review prompt at {request.prompt_path} and "
            f"write the complete markdown review to {request.output_path} "
            "(overwrite). Follow the prompt's section headings. Each finding "
            "must be a '- ' bullet. When the output file is written and "
            "non-empty, exit this Claude process so Spoon can resume the same "
            "session for the next review turn."
        )

    def _accept_review_file(self, output_path: Path) -> AdapterResult | None:
        if not output_path.is_file():
            return None
        text = read_text(output_path)
        if not text.strip():
            return None
        groups = classify_review_text(output_path.name, text)
        if any("[PARSER WARNING]" in item for item in groups["Needs Triage"]):
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message="interactive review would trigger parser warnings",
            )
        return AdapterResult(
            status=AdapterStatus.SUCCESS,
            message="review written via interactive Claude session",
        )

    def _execute_interactive(
        self,
        request: AdapterRequest,
        repo: Path,
        output_path: Path,
        timeout_seconds: int,
    ) -> AdapterResult:
        paths = project_paths(repo)
        run_id = self.session_key or "default"
        try:
            session_id, created_new = ensure_claude_session_id(paths, run_id)
        except Exception as exc:  # noqa: BLE001
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"claude session store error: {exc}",
            )

        # Clear stale output so we wait for a fresh write this turn.
        if output_path.is_file() and read_text(output_path).strip():
            write_text(output_path, "")

        prompt_text = self._interactive_prompt(
            request, created_new=created_new)
        cmd = self._build_interactive_cmd(
            repo,
            session_id=session_id,
            created_new=created_new,
            prompt_text=prompt_text,
        )
        resolved = resolve_terminal(
            self.terminal, cwd=repo, inner_argv=cmd)
        if resolved.launcher == "inline" or resolved.argv is None:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=(
                    "interactive Claude requires an external terminal "
                    f"(got {resolved.note}); set terminal.launcher or ui=print"
                ),
            )

        mode = "new" if created_new else "resume"
        sys.stderr.write(
            f"spoon: opening interactive Claude ({resolved.note}) "
            f"{mode} session={session_id} "
            f"title={self.conversation_title or 'Spoon'}\n"
        )
        sys.stderr.flush()
        try:
            launch_external_terminal(resolved, cwd=repo)
            wait_for_nonempty_file(
                output_path,
                timeout_seconds=timeout_seconds,
                stable_seconds=1.0,
            )
        except TimeoutError:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=(
                    f"timed out after {timeout_seconds}s waiting for "
                    f"{request.output_path}"
                ),
            )
        except OSError as exc:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"failed to launch terminal: {exc}",
            )

        accepted = self._accept_review_file(output_path)
        if accepted is not None:
            return accepted
        return AdapterResult(
            status=AdapterStatus.FAILED,
            message="interactive Claude produced empty or invalid review",
        )

    def _build_cmd(
        self,
        repo: Path,
        capabilities: ClaudeCapabilities,
        use_schema: bool,
        *,
        stream: bool,
    ) -> list[str]:
        output_format = "stream-json" if stream else "json"
        cmd: list[str] = [self.command, "-p", "--output-format", output_format]
        if stream and capabilities.partial_messages:
            cmd.append("--include-partial-messages")
        if stream:
            cmd.append("--verbose")
        if use_schema:
            cmd.extend(["--json-schema", json.dumps(REVIEW_JSON_SCHEMA)])
        if self.model:
            cmd.extend(["--model", self.model])
        if self.conversation_title:
            cmd.extend(["--name", self.conversation_title])
        if self.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", format(self.max_budget_usd, "f")])
        cmd.extend(["--add-dir", str(repo.resolve())])
        return cmd

    def _write_review_if_allowed(
        self,
        output_path: Path,
        rendered: str,
    ) -> AdapterResult | None:
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
        return None

    def _finalize_payload(
        self,
        payload: dict[str, str],
        output_path: Path,
    ) -> AdapterResult:
        try:
            rendered = render_claude_review(payload)
            groups = classify_review_text(output_path.name, rendered)
            if any("[PARSER WARNING]" in item for item in groups["Needs Triage"]):
                raise ValueError(
                    "rendered review would trigger parser warnings")
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

        blocked = self._write_review_if_allowed(output_path, rendered)
        if blocked is not None:
            return blocked
        return AdapterResult(status=AdapterStatus.SUCCESS, message="review written")

    def _execute_visible(
        self,
        cmd: list[str],
        repo: Path,
        prompt_text: str,
        output_path: Path,
        timeout_seconds: int,
    ) -> AdapterResult:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=repo,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"claude command not found: {self.command}",
            )

        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(prompt_text)
        proc.stdin.close()

        captured_lines: list[str] = []
        stderr_chunks: list[str] = []

        sys.stderr.write("spoon: Claude review starting...\n")
        sys.stderr.flush()

        def _stdout_reader() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                captured_lines.append(line.rstrip("\n"))
                human = _humanize_stream_json_line(line)
                if human:
                    sys.stderr.write(human)
                    sys.stderr.flush()

        def _stderr_reader() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_chunks.append(line)
                sys.stderr.write(line)
                sys.stderr.flush()

        stdout_thread = threading.Thread(target=_stdout_reader, daemon=True)
        stderr_thread = threading.Thread(target=_stderr_reader, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        try:
            returncode = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"claude command timed out after {timeout_seconds}s",
            )
        stdout_thread.join()
        stderr_thread.join()

        stderr_text = "".join(stderr_chunks)
        auth_text = f"{stderr_text}\n" + "\n".join(captured_lines)
        if returncode != 0:
            if AUTH_FAILURE_RE.search(auth_text):
                return AdapterResult(
                    status=AdapterStatus.UNAVAILABLE,
                    message="claude authentication failed",
                )
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"claude exited with code {returncode}",
            )

        try:
            payload = _parse_stream_json_lines(captured_lines)
        except ValueError as exc:
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"invalid claude review json: {exc}",
            )
        return self._finalize_payload(payload, output_path)

    def _execute_external_visible(
        self,
        cmd: list[str],
        repo: Path,
        prompt_text: str,
        output_path: Path,
        timeout_seconds: int,
    ) -> AdapterResult:
        work = Path(tempfile.mkdtemp(prefix="spoon-claude-vis-"))
        job_path = work / "job.json"
        capture_path = work / "capture.jsonl"
        exit_path = work / "exit.txt"
        prompt_file = work / "prompt.txt"
        write_text(prompt_file, prompt_text)
        write_visible_job(
            job_path,
            cmd=cmd,
            cwd=repo,
            prompt_path=prompt_file,
            capture_path=capture_path,
            exit_path=exit_path,
        )
        resolved = resolve_terminal(
            self.terminal, cwd=repo, job_path=job_path)
        if resolved.launcher == "inline" or resolved.argv is None:
            sys.stderr.write(
                f"spoon: external terminal unavailable ({resolved.note}); "
                "falling back to inline stream\n"
            )
            sys.stderr.flush()
            return self._execute_visible(
                cmd, repo, prompt_text, output_path, timeout_seconds)

        sys.stderr.write(
            f"spoon: opening Claude in {resolved.note}\n"
        )
        sys.stderr.flush()
        try:
            launch_external_terminal(resolved, cwd=repo)
            returncode = wait_for_exit_file(
                exit_path, timeout_seconds=timeout_seconds)
        except TimeoutError:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"claude command timed out after {timeout_seconds}s",
            )
        except OSError as exc:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"failed to launch terminal: {exc}",
            )

        capture_text = read_text(
            capture_path) if capture_path.is_file() else ""
        captured_lines = capture_text.splitlines()
        auth_text = capture_text
        if returncode != 0:
            if AUTH_FAILURE_RE.search(auth_text):
                return AdapterResult(
                    status=AdapterStatus.UNAVAILABLE,
                    message="claude authentication failed",
                )
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"claude exited with code {returncode}",
            )
        try:
            payload = _parse_stream_json_lines(captured_lines)
        except ValueError as exc:
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"invalid claude review json: {exc}",
            )
        return self._finalize_payload(payload, output_path)

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

        use_interactive = (
            self.ui == "interactive"
            and self.visible
            and self.terminal.launcher != "inline"
        )
        if use_interactive:
            return self._execute_interactive(
                request,
                repo,
                output_path,
                request.timeout_seconds,
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

        use_visible = (
            self.visible
            and capabilities.stream_json
            and capabilities.partial_messages
        )
        if use_visible:
            cmd = self._build_cmd(repo, capabilities, use_schema, stream=True)
            if self.terminal.launcher == "inline":
                result = self._execute_visible(
                    cmd,
                    repo,
                    prompt_text,
                    output_path,
                    request.timeout_seconds,
                )
            else:
                result = self._execute_external_visible(
                    cmd,
                    repo,
                    prompt_text,
                    output_path,
                    request.timeout_seconds,
                )
            if result.status == AdapterStatus.FAILED and "invalid claude review json" in result.message:
                pass
            else:
                return result

        cmd = self._build_cmd(repo, capabilities, use_schema, stream=False)
        # Pass the prompt through stdin rather than as a trailing positional
        # argument. Some claude builds treat --add-dir as variadic
        # (`<directories...>`) and would otherwise swallow the prompt, leaving
        # the CLI with no input.
        try:
            proc = subprocess.run(
                cmd,
                cwd=repo,
                input=prompt_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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
        return self._finalize_payload(payload, output_path)

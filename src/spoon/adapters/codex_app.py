from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..io_util import read_json, write_json_atomic, write_text
from ..paths import ProjectPaths, project_paths
from ..review_parser import classify_review_text
from ..runner.events import append_event
from ..sanitize import redact_secrets
from .base import AdapterRequest, AdapterResult, AdapterStatus
from .command_util import resolve_executable

THREAD_NAME_SET_METHOD = "thread/name/set"
APP_LAUNCH_TIMEOUT_SECONDS = 60
APP_SERVER_CONNECT_RETRIES = 5
APP_SERVER_CONNECT_DELAY_SECONDS = 2.0
# Kept as aliases for older tests / imports.
PROXY_CONNECT_RETRIES = APP_SERVER_CONNECT_RETRIES
PROXY_CONNECT_DELAY_SECONDS = APP_SERVER_CONNECT_DELAY_SECONDS

_APPROVAL_METHODS = frozenset(
    {
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "item/permissions/requestApproval",
    }
)
_ELICITATION_METHODS = frozenset(
    {
        "mcpServer/elicitation/request",
    }
)


class CodexThreadsCorruptError(Exception):
    """Raised when codex-threads.json exists but is invalid."""


def _load_codex_threads(paths: ProjectPaths) -> dict[str, str]:
    if not paths.codex_threads.exists():
        return {}
    raw = read_json(paths.codex_threads)
    if not isinstance(raw, dict):
        raise CodexThreadsCorruptError(
            "codex-threads.json must be a JSON object")
    mapping: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CodexThreadsCorruptError(
                "codex-threads.json must map strings to strings")
        mapping[key] = value
    return mapping


def _save_codex_thread(paths: ProjectPaths, thread_key: str, thread_id: str) -> None:
    mapping = _load_codex_threads(paths)
    mapping[thread_key] = thread_id
    write_json_atomic(paths.codex_threads, mapping)


def _normalize_dir(path: Path) -> Path:
    return path.resolve()


def _resolve_codex_cwd(working_directory: Path, project_map: dict[str, str]) -> Path:
    normalized = _normalize_dir(working_directory)
    for key, target in project_map.items():
        if _normalize_dir(Path(key)) == normalized:
            return _normalize_dir(Path(target))
    return normalized


def _conversation_thread_name(title: str) -> str:
    text = title.strip()
    return text or "Spoon:current"


def _thread_from_list_entry(item: object) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    nested = item.get("thread")
    if isinstance(nested, dict):
        return nested
    if isinstance(item.get("id"), str):
        return item
    return None


def _find_thread_id_by_name(
    listed: dict[str, object],
    unique_name: str,
) -> str | None:
    threads = listed.get("data")
    if not isinstance(threads, list):
        return None
    for item in threads:
        thread = _thread_from_list_entry(item)
        if thread is None:
            continue
        if thread.get("name") == unique_name and isinstance(thread.get("id"), str):
            return thread["id"]
    return None


def _open_codex_thread_url(url: str) -> None:
    """Open a ``codex://threads/<id>`` deep link in the Desktop app."""
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return
    subprocess.run(
        ["xdg-open", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )


def _write_review_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, text)


class _JsonRpcClient:
    def __init__(self, proc: subprocess.Popen[str], *, deadline: float) -> None:
        self._proc = proc
        self._deadline = deadline
        self._next_id = 1
        self._lock = threading.Lock()
        self._line_queue: queue.Queue[str | None] = queue.Queue()
        assert proc.stdin is not None
        assert proc.stdout is not None
        self._stdin = proc.stdin
        self._stdout = proc.stdout
        self._stderr = proc.stderr
        self._reader = threading.Thread(target=self._fill_queue, daemon=True)
        self._reader.start()
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def close(self) -> None:
        if self._proc.stdin is not None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        for stream in (self._stdout, self._stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass
        self._reader.join(timeout=2)
        self._stderr_thread.join(timeout=2)

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._write(payload)

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            self._write(payload)
            return self._read_until_response(request_id)

    def _fill_queue(self) -> None:
        try:
            for line in self._stdout:
                self._line_queue.put(line)
        finally:
            self._line_queue.put(None)

    def _drain_stderr(self) -> None:
        if self._stderr is None:
            return
        try:
            for _line in self._stderr:
                pass
        except OSError:
            return

    def _remaining_seconds(self) -> float:
        return self._deadline - time.monotonic()

    def _read_line(self) -> str:
        remaining = self._remaining_seconds()
        if remaining <= 0:
            raise TimeoutError("codex app-server timed out")
        try:
            line = self._line_queue.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("codex app-server timed out") from exc
        if line is None:
            detail = ""
            code = self._proc.poll()
            if code is not None:
                detail = f" (exit {code})"
            raise RuntimeError(f"codex app-server closed stdout{detail}")
        return line

    def _write(self, payload: dict[str, object]) -> None:
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self._stdin.write(line)
        self._stdin.flush()

    def _respond(self, request_id: object, result: dict[str, object]) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _handle_server_request(self, data: dict[str, object]) -> bool:
        """Answer server→client requests. Returns True when handled."""
        method = data.get("method")
        request_id = data.get("id")
        if request_id is None or not isinstance(method, str):
            return False
        if method in _APPROVAL_METHODS:
            # Headless review turns: accept workspace actions so the turn can finish.
            self._respond(request_id, {"decision": "accept"})
            return True
        if method in _ELICITATION_METHODS:
            # Spoon cannot collect interactive MCP form/url input; decline cleanly.
            self._respond(request_id, {"action": "decline", "content": None})
            return True
        # Avoid hanging the turn on unrecognized server→client requests.
        self._write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not handled by spoon: {method}",
                },
            }
        )
        return True

    def _dispatch_incoming(self, data: dict[str, object]) -> dict[str, object] | None:
        if "method" in data and "id" in data and "result" not in data and "error" not in data:
            self._handle_server_request(data)
            return None
        return data

    def _read_until_response(self, request_id: int) -> dict[str, object]:
        while True:
            line = self._read_line()
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                continue
            data = self._dispatch_incoming(data)
            if data is None:
                continue
            if data.get("id") == request_id:
                if "error" in data:
                    raise RuntimeError(
                        f"json-rpc error: {redact_secrets(str(data['error']))}"
                    )
                result = data.get("result")
                if isinstance(result, dict):
                    return result
                return {"value": result}

    def collect_turn_text(self) -> str:
        chunks: list[str] = []
        while True:
            line = self._read_line()
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                continue
            data = self._dispatch_incoming(data)
            if data is None:
                continue
            method = data.get("method")
            if method == "turn/completed":
                break
            if method == "item/completed":
                params = data.get("params")
                if isinstance(params, dict):
                    text = _extract_agent_message(params)
                    if text:
                        chunks.append(text)
        return "\n".join(chunk for chunk in chunks if chunk).strip()


def _extract_agent_message(params: dict[str, object]) -> str:
    item = params.get("item")
    if not isinstance(item, dict):
        return ""
    if item.get("type") != "agentMessage":
        return ""
    for key in ("text", "message", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class CodexAppServerAdapter:
    def __init__(
        self,
        command: str = "codex",
        project_map: dict[str, str] | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        service_tier: str | None = None,
        conversation_title: str = "Spoon:current",
        thread_key: str | None = None,
    ) -> None:
        self.command = command
        self.project_map = dict(project_map or {})
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier
        self.conversation_title = _conversation_thread_name(conversation_title)
        self.thread_key = thread_key

    def _thread_model_overrides(self) -> dict[str, object]:
        # thread/start accepts model; effort/service tier belong on turn/start.
        if self.model:
            return {"model": self.model}
        return {}

    def _turn_model_overrides(self) -> dict[str, object]:
        overrides: dict[str, object] = {}
        if self.model:
            overrides["model"] = self.model
        if self.reasoning_effort:
            overrides["effort"] = self.reasoning_effort
        if self.service_tier:
            # app-server protocol uses camelCase for this field.
            overrides["serviceTier"] = self.service_tier
        return overrides

    def execute(self, request: AdapterRequest) -> AdapterResult:
        repo = Path(request.working_directory)
        paths = project_paths(repo)
        prompt_path = repo / request.prompt_path
        output_path = repo / request.output_path
        if not prompt_path.is_file():
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"prompt file not found: {request.prompt_path}",
            )

        cwd = _resolve_codex_cwd(repo, self.project_map)
        short_prompt = (
            f"Read the review prompt at {request.prompt_path} and write findings to "
            f"{request.output_path}. Reply with markdown review sections only."
        )

        try:
            review_text = self._run_app_server(
                paths,
                request,
                cwd,
                short_prompt,
                request.timeout_seconds,
            )
            return self._write_success(output_path, review_text)
        except Exception as exc:
            # Desktop path only: do not silently fall back to `codex exec`
            # (that hides Desktop and makes hosts claim "Desktop unavailable"
            # after a different failure). Surface the real app-server error.
            safe_reason = redact_secrets(str(exc))
            message = f"codex app-server failed: {safe_reason}"
            print(f"spoon: {message}", file=sys.stderr, flush=True)
            append_event(
                paths,
                "codex_desktop_failed",
                {
                    "action_id": request.action_id,
                    "reason": safe_reason,
                },
            )
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=message,
            )

    def _write_success(
        self,
        output_path: Path,
        review_text: str,
    ) -> AdapterResult:
        if not review_text.strip():
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message="codex returned empty review text",
            )
        groups = classify_review_text(output_path.name, review_text)
        if any("[PARSER WARNING]" in item for item in groups["Needs Triage"]):
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message="codex review would trigger parser warnings",
            )
        _write_review_atomic(output_path, review_text.rstrip() + "\n")
        return AdapterResult(status=AdapterStatus.SUCCESS, message="review written")

    def _launch_codex_app(self, cwd: Path) -> None:
        """Best-effort Desktop open so the user can watch the thread.

        ``codex app-server daemon`` / ``proxy`` are Unix-oriented and fail on
        Windows. Spoon therefore drives JSON-RPC over ``app-server --stdio``
        (sessions land under ``~/.codex/sessions``). Launching the Desktop app
        is optional UX only and must not block the adapter.
        """
        try:
            subprocess.Popen(
                [resolve_executable(self.command), "app", str(cwd.resolve())],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"codex command not found: {self.command}") from exc
        except OSError as exc:
            print(
                f"spoon: could not launch codex app (continuing with app-server): {exc}",
                file=sys.stderr,
                flush=True,
            )

    def _nudge_desktop_refresh(
        self,
        cwd: Path,
        *,
        thread_id: str | None = None,
    ) -> None:
        """Best-effort Desktop open after an external app-server turn.

        Codex has no public invalidate/refresh RPC (openai/codex#21177). Focus
        alone is not enough when Desktop is on another project or the new
        thread was never assigned into the sidebar. Prefer the documented
        ``codex://threads/<id>`` deep link, then re-open the workspace.
        """
        url = f"codex://threads/{thread_id}" if thread_id else None
        if url is not None:
            try:
                _open_codex_thread_url(url)
                print(
                    f"spoon: opened Codex Desktop thread {self.conversation_title} ({url})",
                    file=sys.stderr,
                    flush=True,
                )
            except OSError as exc:
                print(
                    f"spoon: could not open Codex deep link {url}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        try:
            self._launch_codex_app(cwd)
        except RuntimeError:
            return
        if sys.platform != "win32":
            return
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "$w = New-Object -ComObject WScript.Shell; "
                        "[void]$w.AppActivate('Codex'); "
                        "[void]$w.AppActivate('ChatGPT')"
                    ),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return

    def _open_app_server_client(self, cwd: Path, *, deadline: float) -> _JsonRpcClient:
        # Prefer stdio transport: works on Windows. ``app-server proxy`` needs a
        # Unix control socket / daemon that Codex does not support on Windows.
        proc = subprocess.Popen(
            [resolve_executable(self.command), "app-server", "--stdio"],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return _JsonRpcClient(proc, deadline=deadline)

    def _handshake(self, client: _JsonRpcClient) -> None:
        client.request(
            "initialize",
            {
                "clientInfo": {"name": "spoon", "version": "0.2.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        client.notify("initialized", {})

    def _run_app_server(
        self,
        paths: ProjectPaths,
        request: AdapterRequest,
        cwd: Path,
        prompt_text: str,
        timeout_seconds: int,
    ) -> str:
        overall_deadline = time.monotonic() + timeout_seconds
        self._launch_codex_app(cwd)

        last_error: Exception | None = None
        for attempt in range(APP_SERVER_CONNECT_RETRIES):
            remaining = overall_deadline - time.monotonic()
            if remaining <= 0:
                last_error = TimeoutError("codex app-server timed out")
                break
            if attempt > 0:
                time.sleep(min(APP_SERVER_CONNECT_DELAY_SECONDS, remaining))
                if time.monotonic() >= overall_deadline:
                    last_error = TimeoutError("codex app-server timed out")
                    break
            client: _JsonRpcClient | None = None
            try:
                client = self._open_app_server_client(
                    cwd, deadline=overall_deadline)
                self._handshake(client)
                thread_id = self._resolve_thread_id(
                    client, paths, request, cwd)
                client.request(
                    THREAD_NAME_SET_METHOD,
                    {
                        "threadId": thread_id,
                        "name": self.conversation_title,
                    },
                )
                turn_params: dict[str, object] = {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt_text}],
                }
                turn_params.update(self._turn_model_overrides())
                client.request("turn/start", turn_params)
                review_text = client.collect_turn_text()
                self._nudge_desktop_refresh(cwd, thread_id=thread_id)
                return review_text
            except Exception as exc:
                last_error = exc
            finally:
                if client is not None:
                    client.close()

        raise RuntimeError(
            f"codex app-server unavailable after {APP_SERVER_CONNECT_RETRIES} attempts: {last_error}"
        )

    def _resolve_thread_id(
        self,
        client: _JsonRpcClient,
        paths: ProjectPaths,
        request: AdapterRequest,
        cwd: Path,
    ) -> str:
        thread_key = self.thread_key or request.action_id
        stored = _load_codex_threads(paths)
        existing = stored.get(thread_key)
        if existing:
            return existing

        listed = client.request("thread/list", {"cwd": str(cwd.resolve())})
        matched = _find_thread_id_by_name(listed, self.conversation_title)
        if matched is not None:
            _save_codex_thread(paths, thread_key, matched)
            return matched

        start_params: dict[str, object] = {
            "cwd": str(cwd.resolve()),
            "sandbox": "workspace-write",
        }
        start_params.update(self._thread_model_overrides())
        started = client.request("thread/start", start_params)
        thread = started.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise RuntimeError("thread/start did not return a thread id")
        thread_id = thread["id"]
        _save_codex_thread(paths, thread_key, thread_id)
        return thread_id

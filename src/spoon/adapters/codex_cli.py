from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from ..io_util import read_text, write_text
from ..review_parser import classify_review_text
from .base import AdapterRequest, AdapterResult, AdapterStatus
from .command_util import resolve_executable

AUTH_FAILURE_RE = re.compile(
    r"authentication|not logged in|login required|invalid api key|api key",
    re.IGNORECASE,
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


class CodexCliAdapter:
    def __init__(
        self,
        command: str = "codex",
        visible: bool = False,
        model: str | None = None,
        reasoning_effort: str | None = None,
        service_tier: str | None = None,
    ) -> None:
        self.command = command
        self.visible = visible
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier

    def _build_cmd(self, repo: Path) -> list[str]:
        cmd = [
            resolve_executable(self.command),
            "exec",
            "-C",
            str(repo.resolve()),
            "-s",
            "read-only",
            "--color",
            "never",
        ]
        if self.model:
            cmd.extend(["-m", self.model])
        if self.reasoning_effort:
            cmd.extend(["-c", f"model_reasoning_effort={self.reasoning_effort}"])
        if self.service_tier:
            cmd.extend(["-c", f"service_tier={self.service_tier}"])
        return cmd

    def _finalize_output(
        self,
        output_path: Path,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> AdapterResult:
        auth_text = f"{stderr}\n{stdout}"
        if returncode != 0:
            if AUTH_FAILURE_RE.search(auth_text):
                return AdapterResult(
                    status=AdapterStatus.UNAVAILABLE,
                    message="codex authentication failed",
                )
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"codex exec exited with code {returncode}",
            )

        review_text = stdout.strip()
        if not review_text:
            review_text = stderr.strip()
        if not review_text:
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
        return AdapterResult(status=AdapterStatus.SUCCESS, message="review written via codex exec")

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
                message=f"codex command not found: {self.command}",
            )

        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(prompt_text)
        proc.stdin.close()

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def _stdout_reader() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                stdout_chunks.append(line)
                sys.stderr.write(line)
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
                message=f"codex exec timed out after {timeout_seconds}s",
            )
        stdout_thread.join()
        stderr_thread.join()

        return self._finalize_output(
            output_path,
            returncode,
            "".join(stdout_chunks),
            "".join(stderr_chunks),
        )

    def execute(self, request: AdapterRequest) -> AdapterResult:
        repo = Path(request.working_directory)
        prompt_path = repo / request.prompt_path
        output_path = repo / request.output_path
        if not prompt_path.is_file():
            return AdapterResult(
                status=AdapterStatus.FAILED,
                message=f"prompt file not found: {request.prompt_path}",
            )

        cmd = self._build_cmd(repo)
        prompt_text = read_text(prompt_path)
        if self.visible:
            return self._execute_visible(
                cmd,
                repo,
                prompt_text,
                output_path,
                request.timeout_seconds,
            )

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
                message=f"codex command not found: {self.command}",
            )
        except subprocess.TimeoutExpired:
            return AdapterResult(
                status=AdapterStatus.UNAVAILABLE,
                message=f"codex exec timed out after {request.timeout_seconds}s",
            )

        return self._finalize_output(output_path, proc.returncode, proc.stdout, proc.stderr)

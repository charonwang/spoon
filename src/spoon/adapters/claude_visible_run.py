from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ..io_util import read_json, read_text, write_text
from .claude_cli import _humanize_stream_json_line


def _write_exit(path: Path, code: int) -> None:
    write_text(path, f"{code}\n")


def run_job(job_path: Path) -> int:
    raw = read_json(job_path)
    if not isinstance(raw, dict):
        raise SystemExit("job file must be a JSON object")
    cmd = raw.get("cmd")
    if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
        raise SystemExit("job.cmd must be a string array")
    cwd = Path(str(raw["cwd"]))
    prompt_path = Path(str(raw["prompt_path"]))
    capture_path = Path(str(raw["capture_path"]))
    exit_path = Path(str(raw["exit_path"]))
    prompt_text = read_text(prompt_path)

    print("spoon: Claude review starting in this terminal...", flush=True)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print(
            f"spoon: command not found: {cmd[0]}", file=sys.stderr, flush=True)
        _write_exit(exit_path, 127)
        return 127

    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    proc.stdin.write(prompt_text)
    proc.stdin.close()

    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.rstrip("\n"))
        human = _humanize_stream_json_line(line)
        if human:
            sys.stdout.write(human)
            sys.stdout.flush()
    stderr_text = proc.stderr.read()
    if stderr_text:
        sys.stderr.write(stderr_text)
        sys.stderr.flush()
    code = proc.wait()
    write_text(capture_path, "\n".join(lines) + ("\n" if lines else ""))
    _write_exit(exit_path, int(code))
    print(f"spoon: Claude exited with code {code}", flush=True)
    return int(code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spoon.adapters.claude_visible_run")
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run_job(args.job)
    except Exception as exc:  # noqa: BLE001 — surface to terminal, write exit
        print(f"spoon: visible run failed: {exc}", file=sys.stderr, flush=True)
        try:
            raw = read_json(args.job)
            if isinstance(raw, dict) and "exit_path" in raw:
                _write_exit(Path(str(raw["exit_path"])), 1)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

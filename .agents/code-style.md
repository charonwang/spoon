# code-style

## Language boundary

- Comments and developer-facing explanations: use project-domain terms, describe what the code actually does
- Identifiers, CLI argument names, error prefixes, log keys: English
- Avoid architecture-paper words: no `projection`, `authoritative rebuild`, `revision baseline` — use plain terms that say what the code does

## Comment rules

Only write a comment when:
- The "why" isn't obvious from the code
- There's a concurrency / timing / ordering pitfall
- It's a cross-process or cross-service contract

Otherwise delete it. Don't explain design philosophy in comments.

## Python conventions

- `from __future__ import annotations` at the top of every module
- Type annotations: `str | None` (not `Optional[str]`)
- Dataclasses: `frozen=True` unless mutability is required
- StrEnum for enums that serialize directly to JSON
- Command module function signature: `register(subparsers)` + `run(args: Namespace) -> int`
- Public API functions (e.g. `create_snapshot`) are imported and called directly, not through CLI argparse

## I/O

- All file I/O goes through `io_util.py`: `read_text` / `write_text` / `read_json` / `write_json_atomic`
- `write_json_atomic`: write temp file → `Path.replace()` atomic swap
- Never call `open()` or `json.dump()` directly
- Text files use LF line endings; `io_util` normalizes `\r\n` → `\n` on read/write

## Tests

- Test files: `tests/test_<module_name>.py`
- Use `unittest`, not pytest
- Every command module and runner sub-module needs a corresponding test file

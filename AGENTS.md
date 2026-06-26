# Spoon — Agent Entry

Python 3.11+ CLI for coordinating Cursor, Codex, and Claude Code across plan → review → handoff → archive workflows. File-based shared truth under `.spoon/current/`. Includes a resumable state-machine Runner.

## Architecture

```text
Developer / spoon-orchestrator Skill
  │  spoon run / spoon action
  ▼
CLI (argparse) ──┬── File commands (init/adopt-plan/snapshot/prompts/board/handoff/archive/export-github)
                  │
                  └── Runner engine (spoon run)
                        │  run-state.json / actions.json / events.jsonl
                        ▼
                  Adapters (Claude CLI subprocess / Manual fallback)
                        │
                        ▼
                  .spoon/current/   ← source of truth: brief → plan → review-board → handoff
```

- 9 phases: `brief → plan_adoption → plan_review → plan_decision → implementation → code_review → code_decision → final_check → archive_ready`
- Adapter protocol: `ClaudeCliAdapter` (subprocess, no shell) handles `claude_review`; other kinds go through host action queue, executed by the Skill
- Decision gates only read `review-board.md` structured sections (Blocking / Needs Triage / …), never touching human Decisions
- Runner exit codes: 0 stable / 10 needs_user / 11 needs_host / 20 manual fallback / 21 failure
- All JSON writes: temp file → `Path.replace()` atomic swap
- New command checklist: ① write module in `src/spoon/commands/` ② implement `register(subparsers)` ③ register in `__init__.py`'s `COMMAND_MODULES` ④ add tests
- `io_util.py` is the only file I/O entry point; don't use `open()` or `json.dump()` directly
- JSON writes must be atomic (`write_json_atomic`); corrupt state files must error rather than silently swallow

## Before editing, read completely

- `.agents/code-style.md`
- `.agents/pitfalls.md`
- `.agents/verification.md`

## Key paths

| Path | Content |
|------|---------|
| `src/spoon/cli.py` | argparse entry, iterates COMMAND_MODULES |
| `src/spoon/runner/engine.py` | Runner state machine, `advance()` and `_advance_one()` |
| `src/spoon/runner/model.py` | RunState / WorkflowAction / RunnerResult data classes |
| `src/spoon/runner/gates.py` | Decision gates (plan/code/final check) |
| `src/spoon/paths.py` | ProjectPaths centralized path resolution |
| `src/spoon/io_util.py` | All I/O (LF newlines, atomic JSON, marker replacement) |
| `src/spoon/review_parser.py` | Review Markdown → structured grouping |
| `src/spoon/adapters/base.py` | Adapter Protocol |
| `skills/spoon-orchestrator/SKILL.md` | Stateless host action loop contract |

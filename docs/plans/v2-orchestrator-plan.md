# V2 Orchestrator Implementation Plan

> **Status:** Historical — implemented in `v0.2.0`. Kept for contributor reference.
> **Audience:** Implementers and reviewers.
> **Architecture:** [../architecture.md](../architecture.md)
> **Host actions:** [../host-actions.md](../host-actions.md)
> **Export policy:** [../export-policy.md](../export-policy.md)
> **Roadmap:** [../roadmap.md](../roadmap.md)

## Goal

Add a resumable Runner, portable `spoon-orchestrator` Skill, and reviewable GitHub export. Automate mechanical review and handoff steps; pause only for human judgment.

## Prerequisites (met)

Before Task 1:

```powershell
cd <spoon-checkout>
python -m pip install -e .
python -m unittest discover -s tests -v
```

All seven V1 commands must pass. Importable modules:

```python
from spoon.commands.adopt_plan_cmd import adopt_plan
from spoon.commands.archive_cmd import archive_current
from spoon.commands.board_cmd import generate_board
from spoon.commands.handoff_cmd import generate_handoff
from spoon.commands.prompts_cmd import generate_prompts
from spoon.commands.snapshot_cmd import create_snapshot
```

## Global constraints

- Preserve V1 command interfaces listed above.
- `.spoon/` stays local-only; `init` maintains `.git/info/exclude`.
- V2A–V2D: Python 3.11 stdlib only.
- UTF-8 text, LF newlines.
- Never auto-accept, reject, or rewrite review decisions.
- Never auto-commit business code.
- No `--dangerously-skip-permissions` / `--yolo` on external tools.
- Adapter failure → manual action; never lose workflow state.
- Skill does not depend on Superpowers or other workflow plugins.
- No MCP / Redis / SQLite / message bus in this plan.
- Cursor UI and Codex threads are **host actions**, not Python adapters.
- `experimental_cursor_ui` defaults to `false` in `.spoon/config.json`.
- Raw `.spoon/current/`, patches, logs, transcripts must not be uploaded to GitHub.
- `export-github` writes a candidate directory only — no `git add`, commit, or push.

## Target layout

```text
src/spoon/
  adapters/
    base.py
    claude_cli.py
    manual.py
  runner/
    model.py
    state_store.py
    actions.py
    events.py
    gates.py
    engine.py
  commands/
    run_cmd.py
    action_cmd.py
    export_cmd.py
  export_policy.py
skills/spoon-orchestrator/
  SKILL.md
  references/
    action-kinds.md
    decision-gates.md
github/history-template/
  README.md
  .github/workflows/validate-exports.yml
  scripts/validate_exports.py
tests/
  test_runner_*.py
  test_*_adapter.py
  test_run_action_cli.py
  test_orchestrator_skill.py
  test_github_export.py
  test_v2_acceptance.py
```

## Implementation notes

This public plan is the source of truth for what shipped. Older private design drafts are not published with this repository.

## Tasks

Each task: write failing tests → implement → `python -m unittest discover -s tests -v` green. Do not auto-commit; user commits manually.

### Task 1 — Runner state model and persistence

**Deliverables:** `runner/model.py`, `runner/state_store.py`; extend `paths.py` and `init_cmd.py`.

- Types: `RunPhase`, `RunStatus`, `ActionKind`, `ActionStatus`, `RunState`, `WorkflowAction`, `ImplementationRecord`
- `load_run_state` / `save_run_state`, `load_implementation` / `save_implementation`
- `ProjectPaths`: add `run_state`, `actions`, `events`, `implementation`, `config`
- Atomic JSON via temp file + `Path.replace()`
- `init`: create `config.json` with `{"experimental_cursor_ui": false}` if missing (never overwrite)
- `ImplementationRecord.status` is always `reported_complete`; it does not mean user accepted code

**Tests:** `test_runner_model.py`, `test_runner_state_store.py`, extend `test_init_cmd.py`

---

### Task 2 — Action queue and event log

**Deliverables:** `runner/actions.py`, `runner/events.py`

- `load_actions`, `enqueue_action`, `complete_action`, `fail_action`, `append_event`
- `rebuild_expected_actions` — deterministic ids: `sha256(run_id\\0phase\\0kind\\0prompt\\0output)[:16]`
- Idempotent enqueue; complete requires non-empty output; SHA-256 digest in `action_completed` events
- Missing `actions.json` → rebuild expected actions from current phase and events
- Corrupt `actions.json` → error, preserve file; do not treat as empty queue
- Recover completed status only when event id, output file, and output digest all match

**Tests:** `test_runner_actions.py`

---

### Task 3 — Adapter contract and manual fallback

**Deliverables:** `adapters/base.py`, `adapters/manual.py`

- `Adapter` protocol, `AdapterRequest`, `AdapterResult`, `AdapterStatus`
- `ManualAdapter` → `needs_host` with `spoon action complete` instructions
- Manual payload must include prompt path, output path, and exact completion command

**Tests:** `test_manual_adapter.py`

---

### Task 4 — Review and decision gates

**Deliverables:** `runner/gates.py`

- `plan_review_gate`, `code_review_gate`, `implementation_gate`, `final_check_gate`
- Section-based parsing of `review-board.md` (`Blocking`, `Needs Triage`, …)
- Empty headers and `_None._` must not block; gates do not edit `Decisions`
- Gate checks use structured items only; no whole-file substring matching
- `[CONFLICT]` reaches `Needs Triage` through the V1 review parser

**Tests:** `test_runner_gates.py`

---

### Task 5 — Deterministic workflow engine

**Deliverables:** `runner/engine.py`

- `advance(repo, adapters) -> RunnerResult` — one phase per call
- Phase transitions per [architecture.md](../architecture.md)
- Before `code_review`: `implementation.json` + completed action + post-implementation snapshot event
- Host action kinds: `codex_thread_message`, `cursor_plan_ui`, `cursor_agent_ui`, `manual`
- On exception: status `failed`, exit `21` (do not catch `KeyboardInterrupt` / `SystemExit`)
- If `actions.json` is missing, call `rebuild_expected_actions`; if corrupt, return exit `21`

**Tests:** `test_runner_engine.py`

---

### Task 6 — Claude CLI adapter

**Deliverables:** `adapters/claude_cli.py`

- Subprocess, no shell; verify `claude --help` on target machine for flags
- Structured JSON: `verdict`, `summary`, `findings_markdown` → neutral Markdown review file
- Generated reviews must pass `classify_review_text()` without `[PARSER WARNING]`
- Render verdict under `## Verdict`, not as a bare `Verdict: approved` line
- If `--json-schema` or equivalent structured-output support is missing, fall back to prompt-level JSON instructions plus local validation
- Unavailable → engine exit `20` + manual action

**Tests:** `test_claude_cli_adapter.py` (mock subprocess)

---

### Task 7 — `run` and `action` CLI

**Deliverables:** `commands/run_cmd.py`, `commands/action_cmd.py`

```text
spoon run [--repo PATH] [--continue] [--json]
spoon action list|complete|fail ...
```

- JSON output: `exit_code`, `phase`, `status`, `pending_decision`, `actions`
- `--continue` requires existing `run-state.json`
- `action complete`: path safety inside repo; implementation actions write `implementation.json` atomically
- `action complete` must reject path traversal and undeclared outputs
- Implementation marker write must not split from action completion

**Tests:** `test_run_action_cli.py`

---

### Task 8 — `spoon-orchestrator` Skill

**Deliverables:** `skills/spoon-orchestrator/SKILL.md` + references

- Loop around `spoon run --json`; pause on exit `10`; host actions on `11`/`20`
- Static contract tests: no Superpowers, no auto-commit, default no Cursor UI automation
- Follow [host-actions.md](../host-actions.md) for Codex, Cursor, and manual fallback semantics
- Never paste full plan/review bodies when a path is enough

**Tests:** `test_orchestrator_skill.py`

---

### Task 9 — End-to-end acceptance

**Deliverables:** `test_v2_acceptance.py`, README updates

- Full temp-repo flow through `archive_ready` without git commit
- Failure recovery: timeout, bad JSON, duplicate run/complete, missing output, corrupt/missing `actions.json`
- Verify implementation action completion writes `implementation.json`, then a fresh snapshot is required before code review
- Verify repeated runs do not duplicate actions or review files

---

### Task 10 — GitHub export

**Deliverables:** `export_policy.py`, `commands/export_cmd.py`, `github/history-template/`

- `build_github_export`, `scan_export_tree`, `spoon export-github`
- Allowlist / blocklist per [export-policy.md](../export-policy.md)
- Reuse `path_policy.rewrite_local_links_for_export`
- Blocking findings → no output dir; warnings → `export-report.md`
- History template CI rejects forbidden patterns (shared rules with `export_policy`)
- `snapshot-summary.json` must include `raw_snapshots_exported: false`
- No Git or GitHub write operations

**Tests:** `test_github_export.py`

---

## Manual acceptance checklist

In a disposable Git repo:

```powershell
spoon init --repo <path>
spoon run --repo <path> --json
```

Verify:

- [ ] Runner does not change human board decisions
- [ ] Restart resumes from `run-state.json`
- [ ] Repeated runs do not duplicate actions or reviews
- [ ] Claude failure yields executable manual action
- [ ] Host actions include exact paths
- [ ] `git status` shows no `.spoon/` tracked files
- [ ] No commit created
- [ ] `export-github` excludes raw snapshots, absolute paths, session/thread ids
- [ ] History template CI rejects forbidden files

## MCP (out of scope)

See [roadmap.md](../roadmap.md#mcp-gate-v2e). Implement only after three real V2 workflows and documented need for multi-client action queue access.

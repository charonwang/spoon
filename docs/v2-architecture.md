# Spoon V2 Architecture

V2 adds an orchestration layer on top of V1 file commands. This document is the design contract for implementers; it does not describe shipped behavior until V2 code is released.

Companion contracts:

- [Host actions](host-actions.md)
- [GitHub export policy](export-policy.md)
- [Implementation plan](plans/v2-orchestrator-plan.md)

## Design principles

1. **Files are truth** — Plans, reviews, board decisions, handoffs, and snapshots stay human-readable under `.spoon/current/`.
2. **Runner owns phase state** — `run-state.json`, `actions.json`, and `events.jsonl` are derived control plane; they never replace Markdown artifacts.
3. **Deterministic Python, opportunistic hosts** — The engine advances one phase per `spoon run` call. Claude runs in-process via adapters; Codex threads and Cursor UI are host actions executed by the Skill.
4. **Fail open to manual** — Adapter or UI failures produce explicit manual actions; workflow state is never dropped.
5. **Humans keep judgment** — Gates pause on blocking findings, triage items, and explicit decisions. Spoon does not rewrite the `Decisions` section.

## Component diagram

```text
                    ┌─────────────────────────────────────┐
                    │  Human / spoon-orchestrator Skill   │
                    │  (Codex thread, Cursor UI, manual)  │
                    └──────────────┬──────────────────────┘
                                   │ complete / fail actions
                                   ▼
┌──────────────┐    spoon run     ┌──────────────────────────────┐
│  spoon CLI   │ ───────────────► │  Runner engine (deterministic)│
│  run/action  │ ◄─────────────── │  gates · state · action queue │
└──────────────┘    exit codes    └──────────────┬───────────────┘
                                                 │
              ┌──────────────────────────────────┼──────────────────────────┐
              ▼                                  ▼                          ▼
     ┌─────────────────┐               ┌─────────────────┐        ┌─────────────────┐
     │ V1 commands     │               │ Adapters        │        │ .spoon/current/ │
     │ snapshot        │               │ claude_cli      │        │ brief plan board  │
     │ prompts board   │               │ manual          │        │ handoff reviews   │
     │ handoff archive │               └─────────────────┘        │ snapshots + V2 JSON│
     └─────────────────┘                                            └─────────────────┘
```

## Workflow phases

The Runner walks a fixed phase graph. Each `advance()` call moves at most one persistent phase forward.

```text
brief
  → plan_adoption          (brief exists, plan missing → adopt or wait)
  → plan_review            (plan exists → generate reviews)
  → plan_decision          (reviews complete → board + user gate)
  → implementation         (approved handoff exists)
  → code_review            (implementation.json + fresh snapshot)
  → code_decision          (code reviews + user gate)
  → final_check            (accepted items addressed)
  → archive_ready          (ready for spoon archive; no auto-commit)
```

`implementation.json` with `status: reported_complete` only means the implementation **host action** finished and a snapshot was refreshed — not that the user accepted the code.

## Local layout (V2 additions)

```text
.spoon/
  config.json                    # local only; experimental_cursor_ui (default false)
  current/
    …                            # V1 files unchanged
    run-state.json               # phase, status, pending_decision
    actions.json                 # pending / completed workflow actions
    events.jsonl                 # append-only audit log
    implementation.json          # host-reported implementation complete
```

`config.json` and the rest of `.spoon/` stay out of Git via `.git/info/exclude`.

## State model (summary)

### RunState (`run-state.json`)

| Field | Role |
| --- | --- |
| `schema_version` | Migration anchor (starts at `1`) |
| `run_id` | Stable id for this workflow run |
| `phase` | Current `RunPhase` enum value |
| `status` | `ready`, `running`, `needs_host`, `needs_user`, `failed`, `complete` |
| `pending_decision` | Human prompt when status is `needs_user` |
| `last_error` | Last failure message |
| `updated_at` | ISO-8601 timestamp |

### WorkflowAction (`actions.json`)

Each action has a deterministic id (hash of run id, phase, kind, prompt path, output path — no timestamps in ids).

| Field | Role |
| --- | --- |
| `id` | Deterministic action id |
| `kind` | `claude_review`, `codex_thread_message`, `cursor_plan_ui`, `cursor_agent_ui`, or `manual` |
| `status` | `pending`, `completed`, or `failed` |
| `prompt_path` | Prompt or input path |
| `output_path` | Declared output path |
| `working_directory` | Target repository |
| `payload` | Kind-specific metadata |
| `attempts` | Execution attempts |
| `created_at` / `updated_at` | ISO-8601 timestamps |

| Kind | Executed by |
| --- | --- |
| `claude_review` | `ClaudeCliAdapter` in Python |
| `codex_thread_message` | Skill → Codex host |
| `cursor_plan_ui` | Skill → Cursor (experimental only) |
| `cursor_agent_ui` | Skill → Cursor Agent (experimental only) |
| `manual` | Human following Runner instructions |

### Events (`events.jsonl`)

Append-only records: phase changes, action enqueued/completed/failed, queue rebuilds, runner failures. Used for audit and action recovery. `action_completed` events include action id and output SHA-256 digest.

### ImplementationRecord (`implementation.json`)

This file is written only after an implementation action completes.

| Field | Role |
| --- | --- |
| `schema_version` | Starts at `1` |
| `status` | Always `reported_complete` |
| `action_id` | Completed implementation action |
| `completed_at` | ISO-8601 timestamp |
| `summary_path` | Implementation summary output |

It is a host-completion marker, not a code-acceptance decision.

## Adapters

```text
Adapter.execute(request) → AdapterResult
  status: success | needs_host | needs_user | unavailable | failed
  message: str
  action: WorkflowAction | None   # e.g. manual fallback
```

- **Claude CLI** — subprocess, no shell, structured JSON verdict rendered to neutral Markdown under `reviews/`. On `FileNotFoundError`, auth failure, or timeout → `unavailable` → engine emits manual action (exit `20`).
- **Manual** — always `needs_host` with exact `spoon action complete` instructions.

## Decision gates

Gates read **structured sections** of `review-board.md` only (`Blocking`, `Needs Triage`, etc.) — not free-text substring search. They may call `generate_board()` first but must not edit human `Decisions`.

| Gate | Blocks when |
| --- | --- |
| `plan_review_gate` | Missing reviews, non-empty Blocking/Triage, `[CONFLICT]` |
| `code_review_gate` | Same pattern for code review phase |
| `implementation_gate` | Handoff / implementation preconditions |
| `final_check_gate` | Remaining P1/P2 or open triage |

Empty section headers and `_None._` placeholders do not block.

## Skill loop (`spoon-orchestrator`)

The Skill holds **no state**. It only:

1. Runs `spoon run --json`
2. On exit `0` — report stable phase and stop
3. On exit `10` — show `pending_decision`, wait for user
4. On exit `11` or `20` — execute pending host actions, write outputs, `spoon action complete`
5. On ambiguity — `spoon action fail` and stop
6. Repeat

Host rules (see Skill `references/action-kinds.md` when added):

- **Codex** — only existing thread tools; never auto-create threads
- **Cursor Plan UI** — manual by default; experimental mode requires workspace + Plan Mode confirmation
- **Cursor Agent UI** — requires approved `handoff.md`; completes implementation action only; does not auto-approve plans

Detailed action contracts are in [host-actions.md](host-actions.md).

## GitHub export (`spoon export-github`)

Produces a **candidate** tree under `<destination>/tasks/<project>/<task>/` for human review before any Git push.

**Allowlist:** `brief.md`, `plan.md`, `review-board.md`, `handoff.md`, `index.json`, `snapshot-summary.json`, `export-report.md`

**Blocked:** raw snapshots, diffs, test output, transcripts, `session_id` / `thread_id`, long code fences (>60 lines), unresolved local paths.

Local `file:///…` links are rewritten to `repo://<alias>/<relative>#L<n>` using V1 `path_policy`. Blocking findings prevent creating the final directory; warnings are recorded in `export-report.md`.

`snapshot-summary.json` contains counts and pass/fail enums only — no file names, diffs, or paths. `raw_snapshots_exported` is always `false`.

Optional `github/history-template/` supplies CI to validate a separate **spoon-history** repository.

Full export rules are in [export-policy.md](export-policy.md).

## Repository boundaries

| Location | Holds |
| --- | --- |
| Public **spoon** (this repo) | Tool, tests, docs, Skill, releases |
| Optional **spoon-history** | Human-approved redacted exports |
| Your business Git host | Application code, real diffs, CI/CD |

GitHub Issues/Projects may mirror tasks; they are not workflow truth.

## V1 API preserved

V2 must keep calling these Python entry points (names in `spoon.commands.*`):

- `create_snapshot`
- `generate_prompts`
- `generate_board`
- `generate_handoff`
- `adopt_plan`
- `archive_current`

## Persistence rules

- JSON writes: temp file in the same directory, then `Path.replace()` atomically
- Corrupt `actions.json` → exit `21`, do not treat as empty queue
- Missing `actions.json` → rebuild from phase + deterministic ids + event log
- Completed action recovery requires matching `action_completed` event, current output file, and output digest
- Completed action output deleted or digest mismatch → recover action as pending

## Security notes

- Action `complete` resolves output paths inside the repo; rejects traversal and paths outside `.spoon/current/` where required
- External CLI invocations: argument array, no shell, no permission-skipping flags
- Export scanner is deterministic, not a guarantee against all secrets — human review required

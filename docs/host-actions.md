# Spoon Host Actions

Runner actions describe work that Python cannot complete alone. The Runner owns the queue; hosts execute actions and report completion through `spoon action complete` or `spoon action fail`.

This document is the contract for `spoon-orchestrator` and human fallback when using `spoon run`.

## Rules

- The Runner is the only state owner. Host tools must not edit `actions.json` directly.
- Host actions must not rewrite `review-board.md` decisions.
- Host actions must not stage, commit, push, create GitHub Issues, or update Projects.
- That Git rule applies to the host loop itself. An implementation prompt may allow a coding agent
  to create a local checkpoint commit after relevant verification passes, but the host action must
  not run Git commands on the agent's behalf.
- The Runner may enqueue a `manual` fallback action itself (for example when an adapter is unavailable — exit code `20`). The host Skill must not invent fallback actions: on an unknown, ambiguous, unavailable, or unsafe action it runs `spoon action fail` and stops.
- Cursor UI automation is disabled unless `.spoon/config.json` contains `"experimental_cursor_ui": true`.

## Action Fields

Every `WorkflowAction` stores stable fields:

| Field | Meaning |
| --- | --- |
| `id` | Deterministic id from run id, phase, kind, prompt path, output path |
| `kind` | Action kind listed below |
| `status` | `pending`, `completed`, or `failed` |
| `prompt_path` | Prompt or input file, relative to the repo when possible |
| `output_path` | Declared output file |
| `working_directory` | Target repo |
| `payload` | Kind-specific metadata |
| `attempts` | Number of execution attempts |
| `created_at` / `updated_at` | ISO-8601 timestamps |

## Action Kinds

### `claude_review`

Executed by `ClaudeCliAdapter` inside Python.

- Use `subprocess.run([...], shell=False)`.
- Do not pass permission-skipping flags.
- Verify target-machine support with `claude --help`.
- Render review Markdown with `## Verdict`, `## Summary`, and `## Findings`.
- Generated review must not create `[PARSER WARNING]` when passed to `classify_review_text()`.

### `codex_thread_message`

Executed by the host Skill when thread tools are available.

- Use only an explicit thread id or a unique existing thread match.
- Do not create a new thread automatically.
- Send a short instruction plus file paths, not full plan/review bodies.
- Save the reply to the declared `output_path`.
- If multiple threads match or the tool is unavailable, run `spoon action fail` and stop. Do not create a `manual` action — only the Runner enqueues fallbacks.

### `cursor_plan_ui`

Manual by default. Experimental automation may run only when all are true:

- `.spoon/config.json` has `"experimental_cursor_ui": true`.
- The target workspace path is visible and matches the action.
- Cursor is visibly in Plan Mode.
- The action does not approve a plan on behalf of the user.

If any UI check is unclear, run `spoon action fail` and stop. Do not downgrade to a `manual` action — only the Runner enqueues fallbacks.

### `cursor_agent_ui`

Manual by default. Experimental automation may run only when all are true:

- `.spoon/config.json` has `"experimental_cursor_ui": true`.
- `handoff.md` exists and contains approved changes.
- Cursor is visibly in Agent Mode for the target workspace.
- The action only asks Cursor to implement approved handoff items.

When Cursor reports completion, the host completes the implementation action. The Runner then writes `implementation.json` and requires a fresh snapshot before entering code review.

### `manual`

Always supported.

Manual action payloads must include:

- What prompt or input file to read.
- Where to save output.
- The exact continuation command:

```powershell
spoon action complete --id <id> --output <path>
```

Use `spoon action fail --id <id> --message "<reason>"` when the action cannot be completed safely.

## Completion

`spoon action complete` must:

- Reject unknown action ids.
- Reject output paths outside the repo or outside `.spoon/current/` where required.
- Require declared output files to exist and be non-empty.
- Compute an output SHA-256 digest.
- Append `action_completed` to `events.jsonl`.
- Atomically update `actions.json`.

Implementation actions also write `implementation.json` only after action completion has been persisted.

## Recovery

- Missing `actions.json`: rebuild expected actions from current phase and event log.
- Corrupt `actions.json`: return failure and preserve the file.
- Completed output deleted: recover action as pending.
- Completed output digest mismatch: recover action as pending.

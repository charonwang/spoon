---
name: spoon-orchestrator
description: >-
  Loop on `spoon run --json` to execute Spoon Runner host actions and pause for
  human decisions. Use when advancing a Spoon workflow, when exit code is 11 or
  20, or when the user asks to run the Spoon orchestrator.
---

# Spoon Orchestrator

Portable host loop for Spoon Runner workflows. The Runner owns all workflow state; this Skill
holds **no state** and never edits `.spoon/` JSON files directly.

## Hard rules

- Mutate Runner state **only** through `spoon run`, `spoon action list`,
  `spoon action complete`, and `spoon action fail`. Do not edit `actions.json`,
  `run-state.json`, or `events.jsonl` by hand. (Reading prompt files, writing
  declared `output_path` files, and calling Codex/Cursor host tools to execute
  an action are expected — see "Host action execution" below.)
- Do not rewrite human `Decisions` in `review-board.md`.
- Do not stage, commit, push, create GitHub Issues, or update Projects.
- This Git rule applies to the host loop itself. If an implementation prompt allows a coding
  agent to create a local checkpoint commit after relevant verification passes, do not run Git
  commands on that agent's behalf.
- Do not use Superpowers or other external workflow frameworks.
- Cursor Plan/Agent UI automation is **off by default**. Run it only when
  `.spoon/config.json` contains `"experimental_cursor_ui": true` and every
  safety check in [references/action-kinds.md](references/action-kinds.md) passes.
- When sending work to Codex or Cursor, pass **file paths and short instructions
  only**. Never paste full `plan.md`, review bodies, or snapshot diffs when a
  path is enough.

Contract details: [docs/host-actions.md](../../docs/host-actions.md).

## Loop

Repeat until a stop condition below:

1. From the target repository root, run:

   ```powershell
   spoon run --repo <repo> --json
   ```

2. Parse the JSON payload (`exit_code`, `phase`, `status`, `pending_decision`,
   `actions`).

3. Branch on `exit_code`:

   | Code | Meaning | Skill action |
   | --- | --- | --- |
   | `0` | Phase advanced or stable | Report `phase` and `status`, then **stop** unless the user asks to continue |
   | `10` | User decision required | Show `pending_decision` verbatim and **wait** for the user |
   | `11` | Host action pending | Execute pending host actions (see below), then go to step 1 |
   | `20` | Adapter unavailable — pending manual fallback | Execute pending actions (Runner already queued manual instructions), then go to step 1 |
   | `21` | Runner failure | Report `pending_decision` / failure, **stop** |

4. On ambiguity or unsafe host execution, fail the action and stop:

   ```powershell
   spoon action fail --id <id> --message "<reason>"
   ```

## Host action execution

When `exit_code` is `11` or `20`:

1. From the JSON `actions` array, take items with `status: "pending"`.
2. For each action, read `kind`, `prompt_path`, `output_path`, and
   `working_directory`.
3. Confirm `working_directory` resolves to the same repository root as the
   `--repo` target for this loop. If it does not match, fail and stop:

   ```powershell
   spoon action fail --id <id> --message "working_directory does not match target repo"
   ```

4. Execute per [references/action-kinds.md](references/action-kinds.md).
5. Write the declared output file under the repo (non-empty).
6. Complete the action — `--output` must match `output_path` from the action JSON
   exactly:

   ```powershell
   spoon action complete --id <id> --output <output_path>
   ```

7. Return to step 1 of the loop.

Skip `claude_review` actions in host execution — Python runs those inside
`spoon run`.

## User decision pauses (exit `10`)

Exit `10` means the Runner needs a human board or gate decision. Typical cases
are documented in [references/decision-gates.md](references/decision-gates.md).

Do not auto-approve, auto-reject, or edit `review-board.md` on the user's
behalf. Show `pending_decision`, explain which file or section the user should
update, and wait.

## Recovery

- If host output is missing, empty, or wrong: `spoon action fail` with a clear
  message instead of guessing.
- If `spoon action complete` rejects a path or digest: fix the output file and
  retry; do not bypass Runner validation.
- After implementation host completion, the Runner writes `implementation.json`
  and requires a fresh snapshot before code review — do not skip snapshot steps.

---
name: spoon
description: >-
  Start or advance a Spoon workflow from `/spoon <intent>`: write brief/plan,
  loop on `spoon run --json`, execute host actions, and pause for human
  decisions (exit 10/11/20). Use when the user invokes /spoon, asks to run the
  Spoon orchestrator, or Runner needs a host loop.
---

# Spoon

Portable host loop for Spoon Runner workflows. The Runner owns all workflow state; this Skill
holds **no state** and never edits `.spoon/` JSON files directly.

Install once with `spoon skills install` (symlinks into `~/.agents/skills/spoon` and
`~/.claude/skills/spoon`). Do not copy this Skill into each project's `.cursor/skills/`.

When `visible_terminals` is true and `agents.claude.ui` is `interactive` (default),
Claude review opens the Claude Code TUI in an external terminal (`terminal.launcher`).
One Claude session is kept per Spoon run (`--session-id` then `--resume`): the window may
close between turns; the next review reopens the same session. Spoon waits for the review
file. Set `agents.claude.ui` to `print` for the legacy `-p` JSON/stream-json path.
`inline` launcher streams into the Spoon process; Spoon cannot open Cursor's Terminal
panel. Codex Desktop remains separate (`agents.codex.desktop`).

**Cursor is the visible orchestrator.** Run this loop inside Cursor agent chat. Cursor chat
is the visible session for plan adoption, implementation, and narration — no separate Cursor
window is required. Before and after each `spoon run` step, and whenever Claude or Codex
starts or finishes, narrate in chat: which reviewer ran, the target directory, and the
result or fallback path. On exit `20`, quote the adapter/`spoon` stderr message verbatim —
do **not** invent “Desktop unavailable” unless that text appears. Prefer retrying
`spoon run` once before hand-writing a review.

When the user starts via `/spoon <intent>`, treat the current workspace as the repo and
begin the loop immediately. Do not search the filesystem for Spoon installs, skills, or
`import spoon`; use the `spoon` CLI on PATH. Match the intent language for chat replies,
brief/plan prose, and narration (do not translate the intent into English; do not switch
to English only because this Skill text is English).

Startup from intent:

1. If `.spoon/current/brief.md` is missing, run `spoon init` and narrate one short line
   that the layout was initialized. Do not ask for permission to init.
2. Run `spoon config show`. Read the `Confirmation:` line at the end:
   - `Confirmation: needed (...)` → present Config + Environment + Notes, **stop and wait**
     for the user to confirm (or edit `.spoon/config.json` and re-show). Before confirmation,
     do **not** write brief/plan, and do **not** run `spoon prompts`, `spoon snapshot`, or
     `spoon run`. After the user confirms, run `spoon config ack`, then continue.
   - `Confirmation: ok (...)` → do **not** wait; proceed immediately (config unchanged since
     last ack). Still show the report briefly if useful, but do not block.
3. Write `.spoon/current/brief.md` in the intent language. **Goal first line** becomes the
   conversation title (`Spoon:<label>`). Choose it as follows:
   - If the user pointed at a PRD/doc that already has a title (document title, H1, or an
     explicit Title/Name field), use that short title as Goal.
   - Otherwise distill a short product/topic name from the intent.
   - Never paste the raw `/spoon` message into Goal. Put the full intent or PRD detail under
     Constraints / Current Guess (or adopt the plan file as usual).
   Then write a short `.spoon/current/plan.md` in that same language.
4. `spoon prompts` then `spoon snapshot` then loop `spoon run --json` (cwd = this repo).
5. Exit 10 → show `pending_decision`, wait. Exit 0 → brief status, stop unless user continues.
   Never edit Decisions.
6. Only mention Codex Desktop / Claude again if an adapter actually fails after confirmation;
   quote the failure message; one short tip, then stop or retry.

When resuming an in-progress run (exit 10/11/20 host loop, no new `/spoon <intent>` startup),
do **not** repeat the config confirmation gate (even if `Confirmation: needed` — mid-run
resume skips ack; only new `/spoon <intent>` startups honor the digest gate).

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

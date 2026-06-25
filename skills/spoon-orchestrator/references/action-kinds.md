# Host Action Kinds

Reference for `spoon-orchestrator`. Authoritative contract:
[docs/host-actions.md](../../../docs/host-actions.md).

## Shared rules

- Resolve `prompt_path` and `output_path` relative to the repository root.
- Before executing any action, confirm `working_directory` resolves to the same
  repository root as the `--repo` target for this loop. On mismatch, call
  `spoon action fail --id <id> --message "working_directory does not match target repo"`
  and **stop** — do not write files or drive UI in the wrong workspace.
- Read prompts from disk; send **paths plus brief instructions** to host tools,
  not full plan or review bodies.
- Output files must exist, be non-empty, and be written at the declared
  `output_path`.
- `spoon action complete --output` must use the action JSON `output_path`
  exactly — never substitute a different path.
- Unknown, ambiguous, unavailable, or unsafe execution →
  `spoon action fail --id <id> --message "<reason>"` and **stop**. Do not edit
  `actions.json` or invent fallback actions.

## `claude_review`

**Not a host action.** `ClaudeCliAdapter` runs inside `spoon run`. If a pending
`claude_review` appears in JSON, re-run `spoon run --json` — do not invoke
Claude from this Skill.

## `codex_thread_message`

Execute when Codex thread tools are available.

1. Read `prompt_path` locally.
2. Locate an **existing** thread by explicit thread id or a unique name match.
3. Send a short message with the instruction and file paths only.
4. Save the reply to `output_path`.

Never auto-create a new Codex thread. If zero or multiple threads match, or the
tool is unavailable, call:

```powershell
spoon action fail --id <id> --message "Codex thread unavailable or ambiguous"
```

Then **stop**.

## `cursor_plan_ui`

**Manual by default.**

Experimental automation is allowed only when **all** are true:

- `.spoon/config.json` has `"experimental_cursor_ui": true`
- The target workspace path is visible and matches `working_directory`
- Cursor is visibly in Plan Mode
- The action does not approve a plan on the user's behalf

Steps (manual or experimental):

1. Read `prompt_path`.
2. User (or experimental UI) writes output to `output_path` (non-empty).
3. Complete using the declared path from action JSON:

   ```powershell
   spoon action complete --id <id> --output <output_path>
   ```

If any UI check is unclear, call `spoon action fail --id <id> --message "<reason>"`
and **stop**.

## `cursor_agent_ui`

**Manual by default.**

Experimental automation is allowed only when **all** are true:

- `.spoon/config.json` has `"experimental_cursor_ui": true`
- `.spoon/current/handoff.md` exists and contains approved changes
- Cursor is visibly in Agent Mode for the target workspace
- The action only implements approved handoff items — no plan auto-approval

Steps:

1. Read `prompt_path` and `.spoon/current/handoff.md`.
2. Implement approved items; write output to `output_path` (non-empty).
3. Complete using the declared path from action JSON:

   ```powershell
   spoon action complete --id <id> --output <output_path>
   ```

The Runner then writes `implementation.json` and requires a fresh snapshot
before code review.

If implementation cannot be completed safely, call `spoon action fail` and
**stop**.

## `manual`

Always supported. Follow `payload.instructions` exactly. Typical pattern:

1. Read the prompt or input file named in the instructions.
2. Produce output at `output_path`.
3. Complete using the declared path from action JSON:

   ```powershell
   spoon action complete --id <id> --output <output_path>
   ```

Use `spoon action fail --id <id> --message "<reason>"` when completion is not
safe, then **stop**.

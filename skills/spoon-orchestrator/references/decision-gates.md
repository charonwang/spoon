# Decision Gates and Exit 10 Pauses

When `spoon run --json` returns exit code `10`, the Runner needs a **human**
decision. Show `pending_decision` and wait — do not edit Generated Findings or
Decisions on the user's behalf.

Gates read structured sections inside `review-board.md` **Generated Findings**
only. Empty section headers and `_None._` placeholders do not block.

## `plan_review_gate`

Blocks plan review phase when:

- Required review files are missing or empty:
  `reviews/codex-plan.md`, `reviews/claude-plan.md`,
  `reviews/final-plan-review.md`
- Generated Findings has non-empty **Blocking** or **Needs Triage** items
- `[CONFLICT]` markers appear (classified as Needs Triage)

User action: resolve blocking/triage items on the board or finish missing
reviews, then re-run `spoon run --json`.

## `code_review_gate`

Same pattern during code review for:

- `reviews/codex-code.md`, `reviews/claude-code.md`,
  `reviews/cursor-self-review.md`
- Non-empty Blocking / Needs Triage in Generated Findings

## `implementation_gate`

Blocks implementation when:

- `.spoon/current/handoff.md` is missing or empty
- The review board has no approved handoff items

User action: complete plan adoption and handoff approval on the board.

## `final_check_gate`

Blocks archive when:

- Generated Findings still has Blocking or Needs Triage items, or
- **Should Fix** items remain (P1/P2 cleanup)

User action: address remaining findings or explicitly accept risk on the board.

## What not to do on exit 10

- Do not call `spoon action complete` — no host action is pending.
- Do not auto-fill Decisions or accept/reject findings.
- Do not commit or push repository changes.

After the user updates the board or required files, run `spoon run --json`
again.

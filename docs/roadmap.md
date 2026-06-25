# Spoon Roadmap

This document is the public timeline: what shipped and what may come next. Day-to-day usage lives in [usage.md](usage.md) and [design-overview.md](design-overview.md).

## Shipped (`v0.2.0`)

File-based workflow under `.spoon/current/` plus a resumable Runner, host-action Skill, Claude CLI adapter, and redacted GitHub export.

### Workflow commands

| Command | Purpose |
| --- | --- |
| `spoon init` | Create `.spoon/current/` and exclude `.spoon/` via `.git/info/exclude` |
| `spoon adopt-plan` | Move a Cursor plan into `plan.md` |
| `spoon snapshot` | Capture Git status, diffs, tests, dependency checks, sensitive-scan notes |
| `spoon prompts` | Generate reusable review and check prompts |
| `spoon board` | Summarize raw reviews into `review-board.md` |
| `spoon handoff` | Build implementation handoff from accepted board items |
| `spoon archive` | Archive the current task and recreate an empty `current/` |

### Orchestration commands

| Command | Purpose |
| --- | --- |
| `spoon run [--continue] [--json]` | Advance workflow one phase |
| `spoon action list`, `complete`, `fail` | Host action queue |
| `spoon export-github` | Redacted export candidate + history validation template |

Architecture: [architecture.md](architecture.md). Host contracts: [host-actions.md](host-actions.md). Export rules: [export-policy.md](export-policy.md).

### Boundaries (unchanged)

- No staging, committing, or pushing business code
- No reading private chat logs or editor internals
- No automatic accept/reject of review decisions
- Trusted local input for `--test-cmd` and `--dependency-cmd`
- Python 3.11+ stdlib only in the shipped CLI

### Runner exit codes

| Code | Meaning |
| --- | --- |
| `0` | Stable |
| `10` | User decision required |
| `11` | Pending host action |
| `20` | Adapter unavailable → manual action |
| `21` | Runner failure; phase unchanged |

---

## Next

### MCP facade (conditional)

MCP is **out of scope** until at least three real Spoon workflows complete and a concrete need appears for two or more clients to call the action queue directly. If approved later, the facade would expose at most:

```text
get_state
list_actions
complete_action
fail_action
```

All calls must go through existing Runner modules — no second state store.

### Other non-goals

- Redis, SQLite, WebSocket brokers, or message buses
- Auto `git commit`, `push`, Issue creation, or Project updates
- `--dangerously-skip-permissions`, `--yolo`, or equivalent on external tools
- Dual compatibility with `.ai-flow/` (migrate once per repo; see README)
- Cursor UI automation by default (`experimental_cursor_ui` opt-in only)
- Uploading raw `.spoon/current/`, patches, logs, or transcripts to GitHub

---

## How to follow progress

1. Read [architecture.md](architecture.md) for design contracts.
2. Use GitHub [Issues](https://github.com/charonwang/spoon/issues) for actionable work.
3. [plans/v2-orchestrator-plan.md](plans/v2-orchestrator-plan.md) records the original implementation task breakdown.

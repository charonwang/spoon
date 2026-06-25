# Spoon Roadmap

This document describes what Spoon ships today and what is planned next. Implementation tracking lives in GitHub Issues and Milestones; this file is the public direction of travel.

## V1 — Shipped (`v0.1.x`)

**Status:** Released. See [design overview](design-overview.md).

File-based CLI. Humans and AI tools share workflow state under `.spoon/current/` without a database or hosted service.

| Command | Purpose |
| --- | --- |
| `spoon init` | Create `.spoon/current/` and exclude `.spoon/` via `.git/info/exclude` |
| `spoon adopt-plan` | Move a Cursor plan into `plan.md` |
| `spoon snapshot` | Capture Git status, diffs, tests, dependency checks, sensitive-scan notes |
| `spoon prompts` | Generate reusable review and check prompts |
| `spoon board` | Summarize raw reviews into `review-board.md` |
| `spoon handoff` | Build implementation handoff from accepted board items |
| `spoon archive` | Archive the current task and recreate an empty `current/` |

**V1 boundaries (unchanged in V2):**

- No staging, committing, or pushing business code
- No reading private chat logs or editor internals
- No automatic accept/reject of review decisions
- Trusted local input for `--test-cmd` and `--dependency-cmd`

---

## V2 — Orchestrator (planned)

**Goal:** A resumable Runner, optional `spoon-orchestrator` Skill, and reviewable GitHub export — automate mechanical steps, pause only where human judgment is required.

**Prerequisite:** V1 complete with all commands tested and green CI. That prerequisite is met on `main`.

**Truth source:** `.spoon/current/` remains the only workflow source of truth. The Runner owns phase state; the Skill is a stateless host executor.

Detailed architecture: [v2-architecture.md](v2-architecture.md).
Host action contract: [host-actions.md](host-actions.md).
GitHub export policy: [export-policy.md](export-policy.md).
Task breakdown: [plans/v2-orchestrator-plan.md](plans/v2-orchestrator-plan.md).

### Phases

| Phase | Scope | New surface |
| --- | --- | --- |
| **V2A — Runner core** | State model, action queue, events, gates, engine, `spoon run`, `spoon action` | `src/spoon/runner/`, `run-state.json`, `actions.json`, `events.jsonl` |
| **V2B — Claude adapter** | Non-interactive Claude CLI reviews with structured output and manual fallback | `src/spoon/adapters/claude_cli.py` |
| **V2C — Orchestrator Skill** | Portable Markdown Skill for Codex/Cursor host actions | `skills/spoon-orchestrator/` |
| **V2D — GitHub export** | Redacted export candidate + validation template for a history repo | `spoon export-github`, `github/history-template/` |
| **V2E — MCP (conditional)** | Thin facade over Runner only if Skill + CLI prove insufficient | Not started; see [MCP gate](#mcp-gate-v2e) |

V2A–V2D use **Python 3.11 stdlib only** (same as V1).

### Planned commands

```text
spoon run [--repo PATH] [--continue] [--json]
spoon action list [--repo PATH] [--json]
spoon action complete --id ID --output PATH [--repo PATH]
spoon action fail --id ID --message TEXT [--repo PATH]
spoon export-github --repo PATH --destination PATH --project ALIAS --task ID
```

### Runner exit codes

| Code | Meaning |
| --- | --- |
| `0` | Stable; no pending host actions or user decisions |
| `10` | User decision required |
| `11` | Pending host action |
| `20` | Adapter unavailable; manual action generated |
| `21` | Runner failure; persisted phase unchanged |

### Non-goals (V2)

- MCP, Redis, SQLite, WebSocket brokers, or message buses
- Auto-accept / auto-reject / auto-triage of review findings
- Auto `git commit`, `push`, Issue creation, or Project updates
- `--dangerously-skip-permissions`, `--yolo`, or equivalent on external tools
- Dual compatibility with `.ai-flow/` (migrate once per repo; see README)
- Cursor UI automation by default (`experimental_cursor_ui` opt-in only)
- Uploading raw `.spoon/current/`, patches, logs, or transcripts to GitHub

### MCP gate (V2E)

MCP is **out of scope** until at least three real V2 workflows complete and a concrete need appears for two or more clients to call the action queue directly. If approved later, the facade would expose at most:

```text
get_state
list_actions
complete_action
fail_action
```

All calls must go through existing Runner modules — no second state store.

---

## How to follow progress

1. Read [v2-architecture.md](v2-architecture.md) for design contracts.
2. Use GitHub [Issues](https://github.com/charonwang/spoon/issues) for actionable work items.
3. Milestones `V2A` … `V2D` will group tasks when implementation starts.

Documentation-only updates for V2 do not change the installable CLI until code lands in a tagged release.

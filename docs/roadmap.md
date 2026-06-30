# Spoon Roadmap

This document is the public timeline: what shipped and what may come next. Day-to-day usage lives in [usage.md](usage.md) and [design-overview.md](design-overview.md).

## Shipped (`v0.2.0`)

File-based workflow under `.spoon/current/` plus a resumable Runner, host-action Skill, Claude CLI adapter, and redacted GitHub export.

The full v0.2.0 command set (file-workflow commands plus `run`, `action`, and `export-github`) is documented in [usage.md](usage.md).

Architecture: [architecture.md](architecture.md). Host contracts: [host-actions.md](host-actions.md). Export rules: [export-policy.md](export-policy.md).

### Boundaries (unchanged)

- No staging, committing, or pushing business code
- No reading private chat logs or editor internals
- No automatic accept/reject of review decisions
- Trusted local input for `--test-cmd` and `--dependency-cmd`
- Python 3.11+ stdlib only in the shipped CLI

### Runner exit codes

`0` stable, `10` user decision, `11` pending host action, `20` adapter unavailable → manual action, `21` runner failure. Full table: [architecture.md](architecture.md).

---

## Next

### V3 planning: explicit Runner graph

LangGraph's Python overview is a useful reference for long-running, stateful agent workflows:
resume after failure, human pauses, saved state, and run traces. Spoon already implements a
domain-specific, dependency-free subset of the same pattern — the `engine.py` phase machine is a
hardcoded `StateGraph`, `run-state.json`, `actions.json`, and `events.jsonl` together form the local
resume record (recovery also relies on output files and digests), exit `10` (`needs_user`) is an
`interrupt`, and `events.jsonl` is a local trace. This convergence validates the state-machine
direction; it is not a reason to adopt the framework.

**For Spoon, V3 borrows LangGraph's ideas where they map to Spoon's existing files and statuses, without moving the shipped CLI to LangGraph.**
LangGraph orchestrates in-process LLM and tool loops; Spoon deliberately runs no LLM in the CLI and
coordinates external hosts (Cursor, Codex, Claude) through files and an action queue, so the
framework's model/tool/memory machinery does not apply. Concretely:

- Keep `.spoon/current/` files as the source of truth. Do not add a second hidden state store — this
  is exactly the trap a LangGraph checkpointer would spring.
- Keep the shipped CLI on Python 3.11+ stdlib until a real workflow need justifies a dependency.
- Make the Runner phase graph explicit, so phases, gates, host actions, and exit codes can be reviewed as data.
- Record `needs_user` and `needs_host` pauses with the input needed to continue.
- Strengthen recovery around `run-state.json`, `actions.json`, and `events.jsonl` by documenting how a run resumes after missing or changed files.
- Add a low-cost trace or graph command before considering hosted tracing tools.

Deep Agents is a useful comparison, but not a target architecture. Its `interrupt_on`,
subagents, filesystem-backed context, memory files, and skills map loosely to Spoon's gates,
host actions, `.spoon/current/`, `AGENTS.md`, and `spoon-orchestrator` Skill. The useful lesson
for V3 is the pause and delegation rules: declare when a run pauses, record what input is needed to
continue, keep delegated work isolated, and require a readable output artifact. Spoon should keep
those contracts in files and exit codes instead of moving model/tool execution into the CLI.

V3 should compare with durable workflow systems and coding-agent tools, especially Temporal,
OpenHands, SWE-agent, Aider, CrewAI Flows, and Pydantic AI. The goal is not feature parity, but
clearer resume records, host-action boundaries, readable traces, and structured outputs.

MASFactory is a useful reference for the graph authoring and inspection side: keep the fixed Runner
flow readable as a small transition table, use that table to render `spoon graph`, and keep runtime
trace events tied to phase/action/gate names. Spoon should not adopt VibeGraphing, model adapters,
or nested agent graph nodes.

V3 should also borrow from practical agent workflows without binding to a specific toolchain:
challenge the brief before planning, split unknowns into code research and external research, keep
PRD/design/implementation notes separate enough to review, run implementation through a host action,
then finish with an explicit check, reusable-notes step, and archive record. During implementation,
coding agents may check existing plan checklist items and create local checkpoint commits only after
the relevant verification for a completed approved item or review-fix batch passes. Spoon and host
actions still do not perform those Git writes, and they must not push.

Candidate V3 steps:

1. Extract the fixed phase transitions from `engine.py` into a small transition table used by tests
   and docs — the table version of LangGraph's `StateGraph`, with one source of truth for
   phases, gates, and exit codes.
2. Add `spoon graph` or `spoon run --trace` to render the current phase, pending actions, and next
   gate. Rendering the transition table to Mermaid mirrors LangGraph's `get_graph().draw_mermaid()`.
3. Use one pause record shape for user decisions and host actions, carrying the input needed to
   continue — the equivalent of LangGraph's `interrupt` + `Command(resume=...)`.
4. Keep command modules from depending on Runner internals. In particular, revisit the
   implementation base / record read path so `snapshot` does not need to import `runner.state_store`.
5. Revisit LangGraph or another runtime only if Spoon becomes a multi-client service, needs concurrent workflows, or needs hosted workflow inspection.

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
- Spoon or Runner auto `git commit`, `push`, Issue creation, or Project updates
- `--dangerously-skip-permissions`, `--yolo`, or equivalent on external tools
- Cursor UI automation by default (`experimental_cursor_ui` opt-in only)
- Uploading raw `.spoon/current/`, patches, logs, or transcripts to GitHub

---

## How to follow progress

1. Read [architecture.md](architecture.md) for design contracts.
2. Use GitHub [Issues](https://github.com/charonwang/spoon/issues) for actionable work.

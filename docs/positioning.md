# Spoon Positioning (2026)

Spoon is the local **governance layer** for multi-tool coding: shared plan / review /
handoff artifacts, human decision gates, and resumable phases. It is not another
parallel agent farm.

Day-to-day commands: [usage.md](usage.md). Design summary: [design-overview.md](design-overview.md).
What to build next: [roadmap.md](roadmap.md).

## Why Spoon still exists

By mid-2026, multi-agent coding split into three tiers:

| Tier | Job | Typical tools |
| --- | --- | --- |
| 1 — In-process | Subagents / Agent Teams inside one session | Claude Agent Teams, oh-my-claudecode, OmO/Sisyphus |
| 2 — Local orchestrators | Parallel agents in git worktrees + dashboards | Conductor, Vibe Kanban, Claude Squad, Antigravity Mission Control |
| 3 — Cloud async | Assign work, return to a PR | Cursor Background Agents / Glass, Claude Code Web, Copilot Coding Agent, Jules, Codex Web |

Most products optimize **throughput** (more agents writing code). Spoon optimizes
**decision quality and auditability** for one task across Cursor, Codex, and Claude Code:

1. Files under `.spoon/current/` are the shared truth — no shared DB or vendor lock-in.
2. Spoon does not write business code and does not accept or reject review decisions for humans.
3. `review-board.md` carries structured findings; Runner gates never rewrite human `Decisions`.
4. A resumable phase machine plus exit codes (`0` / `10` / `11` / `20` / `21`) give the
   `spoon` Skill a stable host loop.
5. Path and Plan-link conventions stay Windows- and Cursor-friendly.

Use Tier 1–3 tools when the goal is parallel implementation. Use Spoon when the goal is
plan → cross-tool review → human gate → handoff → archive with a readable trail.

## Fit in the emerging stack

Industry practice is composing layers rather than picking one winner:

```text
orchestration surface (Cursor / dashboards)
        │
execution hosts (Claude Code, Codex, …)
        │
verification / governance  ← Spoon lives here
        │
repo files + human decisions
```

Cross-provider review (for example Codex reviewing Claude output) is becoming a product
feature elsewhere. Spoon's job is to keep that review path **file-backed and
decision-gated**, not to own the coding loop.

## Closest neighbors (what to borrow)

| Neighbor | Borrow | Do not absorb |
| --- | --- | --- |
| Forge Orchestrator | Multi-tool shared state; thin MCP over existing APIs; drift checks | File-lock races for parallel writers; a second knowledge store that competes with `.spoon/current/` |
| Cross-provider review plugins (e.g. Codex-in-Claude review commands) | Executor ≠ reviewer as a default path; adversarial review prompts | Binding Spoon to one host's plugin surface |
| Ralph-style loops | Small bounded tasks, verify, reset context, retry caps | Running the implementation loop inside the Spoon CLI |
| LangGraph / Deep Agents ideas | Explicit graph, interrupt/resume shape, local traces | Moving LLM or tool execution into the shipped CLI |
| Conductor / Vibe Kanban | Progress visibility, diff-first review UX | Becoming a parallel coding dashboard |
| AGENTS.md convention | Short, human-owned cross-tool rules | Letting agents rewrite `AGENTS.md` unchecked |
| Skill / skillfold patterns | Compile Spoon contracts into host Skills | Inventing a second configuration language |

Framework comparisons for V3 engineering detail stay in [roadmap.md](roadmap.md).

## Strategic rules

- Compete on governance, not on agent count or worktree spawning.
- Keep adapters valuable only when they improve review intake, digests, and gates —
  not when they merely run more host commands.
- Treat parallel worktrees as optional awareness (snapshots, base SHAs), not as Spoon-owned
  execution.
- Prefer fewer default steps from plan to first human gate over adding more file commands.
- Keep non-goals: no Spoon/Runner `git commit` or `push`, no auto-accept of Decisions,
  no reading private chat logs.

## Recommended defaults

Document and prompt for **executor ≠ reviewer** pairings (for example Claude implements,
Codex reviews, or the reverse). The durable path remains:

```text
prompts → reviews/ → spoon board → human Decisions → spoon handoff → archive
```

## Out of scope for this document

Command reference, phase tables, and host-action contracts belong in [usage.md](usage.md),
[architecture.md](architecture.md), and [host-actions.md](host-actions.md). This page only
records product position and what Spoon should and should not become.

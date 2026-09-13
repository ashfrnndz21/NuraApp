# Nura

A health chief of staff for one person and the family around them. Quiet most days; flawless on the four days a year that matter.

Start with `docs/00-MASTER-BUILD-SPEC.md`. Section 0 is the reading order. `CLAUDE.md` in this folder tells Claude Code how to work here; `TASKS.md` is the ordered list of sessions to run.

Layout:
- `backend/` — Python (FastAPI) services: identity and keys, ingestion, memory, state, reasoning, feed, WhatsApp.
- `ios/` — SwiftUI app (iOS 17+).
- `infra/` — AWS CDK (Python) for Singapore and Malaysia regions.
- `docs/` — every specification, prototype, the backlog and the brand.
- `.claude/` — rules and subagents for Claude Code.

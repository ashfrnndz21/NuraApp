# Building Nura continuously in the background

The idea: the backlog becomes a queue of GitHub Issues; a headless Claude Code agent picks the next ready story, builds it on a branch with tests, and opens a PR; a second agent reviews it against the safety and plain-words rules; CI runs the tests; low-risk PRs merge themselves, high-risk ones wait for you; and a nightly orchestrator promotes the next stories whose dependencies are done and writes you a morning report. You steer by editing issues and merging the gated PRs. Everything else runs while you sleep.

Claude Code has three ways to run without a person at the keyboard, and this design uses all three:
- `claude -p "…"` — headless mode; the full agent, non-interactive, scriptable, with `--allowedTools`, `--max-turns`, `--output-format json` and session resumption.
- `anthropics/claude-code-action@v1` — the official GitHub Action that wraps headless mode with the repo, issue and PR plumbing.
- Subagents with `run_in_background` inside a session, for reviewers and explorers that run in parallel.

Check the current inputs and flags against the docs before first use: https://code.claude.com/docs/en/headless and https://github.com/anthropics/claude-code-action.

---

## 1. The loop

```
feature-backlog.xlsx ──scripts/backlog_to_issues.py──▶ GitHub Issues (one per story, labels: tier, epic, risk, depends-on)
                                                              │
   nightly orchestrator (claude -p) ──────────────────────────┤ promotes ≤3 stories to agent:ready whose deps are merged
                                                              ▼
                                        claude-dev.yml (on label agent:ready)
                                        reads CLAUDE.md + the issue + the spec section
                                        branch E04-03-slug → tests first → implement → make test/lint/plain-words → PR "Closes #N"
                                                              │
                                        claude-review.yml (on PR opened/updated)
                                        runs clinical-safety-reviewer + plain-words-reviewer → posts findings, sets a check
                                                              │
                                        ci.yml: pytest, ruff, mypy, plain-words; xcodebuild test on macOS runners for ios/
                                                              │
                        risk:low + checks green ──▶ auto-merge          risk:high ──▶ waits for you (keys, consent, medicines, reasoning, safety, WhatsApp send)
                                                              │
                                        merged → orchestrator sees the dependency closed → promotes the next
```

Progress report: every morning the orchestrator writes `docs/progress/YYYY-MM-DD.md` (what merged, what is blocked, what it decided not to promote and why) and opens it as a PR so you read it in one place.

## 2. What the agent may and may not do

- May: read the repo and docs, edit files, run `make test`, `make lint`, `make plain-words`, `xcodebuild test`, commit to its own branch, open and update its PR, comment on its issue.
- May not: push to `main`, merge, change `.github/`, `.claude/`, `CLAUDE.md`, migrations of existing tables, anything under `backend/app/keys/` or `backend/app/safety/` without the `risk:high` gate, or touch secrets. Enforced by branch protection, `--allowedTools`, the CODEOWNERS file and a PreToolUse hook that blocks writes to protected paths.
- Budget: `--max-turns 80` per story, one story per run, at most three runs in flight. If a run exhausts its turns it posts what it has as a draft PR and stops; the orchestrator does not retry the same story more than twice without a human comment.

## 3. Risk gates

| Label | Applies to | Merge |
|---|---|---|
| `risk:low` | UI chrome, design tokens, feed rendering, docs, tests, fixtures, non-patient strings | Auto-merge when checks and both reviewers pass |
| `risk:medium` | Ingestion, memory, State, search, delivery ranking | Auto-merge when checks pass and the safety reviewer reports no failures; you get a digest |
| `risk:high` | Keys, consent, audit, medicines, reasoning, safety, WhatsApp outbound, migrations | Never auto-merges. Reviewers post; you merge |

Patient-facing strings are always checked by the plain-words reviewer regardless of risk.

## 4. Secrets and auth

Never in prompts, transcripts or diffs. The Action reads `ANTHROPIC_API_KEY` from repository secrets; on AWS use `use_bedrock: true` with OIDC role assumption instead of a static key. Licensed drug data, WhatsApp provider and AWS credentials are not available to the dev agent at all; it works against fixture clients. Only CI's deploy job holds deploy credentials, and deploy is manual until T1 is on TestFlight.

## 5. Cost and concurrency

Three concurrent runs, 80 turns each, nightly orchestration, and a review run per PR keeps this in the low hundreds of dollars a week at pilot scale. The orchestrator prints the day's spend from the JSON output totals into the progress report so it is visible.

## 6. The human's job

Ten minutes in the morning: read the progress PR, merge the gated PRs, comment on any issue the agent got wrong (the comment becomes context on the next run), and adjust priorities by relabelling. Once a week: run the safety reviewer over `main` as a whole and read the test set accuracy report.

## 7. iOS specifics

macOS runners run `xcodebuild test` on the simulator, so the agent can validate Swift changes headlessly. Signing, TestFlight uploads and anything needing your Apple credentials stay manual. The agent cannot see a simulator screen; UI review is yours, so `ios/` stories default to `risk:medium` with a screenshot step in CI (`xcrun simctl io booted screenshot`) attached to the PR.

## 8. One-off background tasks without the pipeline

For a single task you want to fire and forget from your laptop, `claude -p` in a `nohup` or a cloud session is enough; the pipeline is for the steady state of a backlog with 150 stories.

## 9. Files

- `.github/workflows/claude-dev.yml`, `claude-review.yml`, `ci.yml`, `orchestrator.yml`
- `.github/CODEOWNERS`
- `.claude/commands/next.md`, `.claude/commands/report.md`
- `.claude/hooks/protect-paths.sh` and its `settings.json` entry
- `scripts/backlog_to_issues.py`

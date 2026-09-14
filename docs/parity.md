# iOS-to-web parity

**Audited** 2026-09-15 on `main` at `3431249` · **Scope** every T1 story (`gh issue list --state all --label T1`, 90 issues) against the spec (`docs/00-MASTER-BUILD-SPEC.md` §3 and §7), `TASKS.md` and ADR 0001.

The standing requirement ([ADR 0001](adr/0001-web-first-client.md)) is that the web client has every feature and user story the iOS plan has, like for like. This page says, story by story, where each one lives and what is still owed. It was built by reading the code, not the PR titles. Nothing was built for it.

## How to read the table

- **Issue** is the GitHub state. Several stories are delivered but still open, because a PR body said "Closes #a, #b, #c" and GitHub closes only the first number in such a list (see *Issue state* below). Judge a story by its status, not its issue state.
- **Backend** is the route and module that carry the story, the merged PR, and the test that shows the acceptance.
- **Web** is the screen or component under `web/src` that surfaces it; "none" if nothing on the web does; "n/a (system)" for a service with nothing a person sees.
- **Substitute** is the ADR 0001 stand-in where part of the story is native-only.
- **Checkpoint** is the one in `docs/checkpoints.md` that shows it.
- **Status**:
  - **done**: the acceptance is met in code and a web surface exists, or it is a system story with nothing to surface;
  - **backend-only**: the acceptance is met on the API, a person would use it, and no web screen does;
  - **missing**: part of the acceptance is not met in code (the note says which);
  - **in flight**: covered by open work (#121 delivery; the W4 web polish on #61, #63, #8, #74).

## ADR 0001 substitutes for native-only hooks

| Native-only capability | Web substitute |
|---|---|
| HealthKit device readings | Photo of the device screen (E02-08) and manual entry |
| Lock-screen / Home Screen widget, Live Activity | Home-screen PWA opens on the Now card; emergency card one tap away and printable |
| Share extension "Add to record" | Forward to the WhatsApp agent (E19) |
| Siri / App Intents | None at T1 |
| Assistive Access | The Dad density mode |

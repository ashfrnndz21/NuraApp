# ADR 0001 — Web-first client; native iOS as a later layer

**Date** 2026-09-14 · **Status** accepted · **Decided by** the owner, on the operator's recommendation

## Context

The build plan and TASKS.md Sessions 10–12 assume a native iOS client. Testing that path needs Xcode on a Mac (or a macOS CI runner and an Apple Developer account for TestFlight), and the owner has asked for no local toolchain dependencies. The product's own documents already treat WhatsApp as the patient's channel where his phone is old or Android, and every screen exists as an HTML prototype under `docs/`.

## Decision

The first client is a **web app (PWA)** served by the backend and opened in Safari on the phone, added to the home screen. It must carry **every user story** in the backlog that the iOS client was to carry; the four platform hooks that have no web equivalent (HealthKit, widgets / Live Activities, the share extension, Siri) get the substitutes below and are deferred to a native layer that CI builds without a local Xcode when an Apple account exists.

| Native-only capability | Web substitute |
|---|---|
| HealthKit device readings | Photo of the device screen (E02-08) and manual entry |
| Lock-screen / Home Screen widget, Live Activity | Home-screen PWA opens on the Now card; emergency card one tap away and printable |
| Share extension "Add to record" | Forward to the WhatsApp agent (E19) |
| Siri / App Intents | None at T1 |
| Contacts picker (CNContactPickerViewController) for the "for someone else" door | The Contact Picker API where the browser has it (Chrome on Android); typed entry otherwise, since Safari on iOS has none. The relationship is a set of choices, never typed (E01-01, W6) |
| Assistive Access | The Dad density mode |

Everything else — sign-in, densities and tokens, Today/Now/Taken, feed pager with voice, onboarding, medicines, review cards, visits, memos, family, offline cache of today's medicines and the emergency card, push for doses on iOS 16.4+ — ships on the web with the same backend.

## Consequences

- A `web/` directory (TypeScript, Vite, a small component layer, Playwright tests in CI) beside `backend/` and `ios/`; served by the backend in dev and by the deployment.
- Checkpoints 9 and 10 become "open this URL on your phone"; checkpoint 11 (TestFlight) moves after the web track.
- The iOS stories stay in the backlog labelled `after-web`; `ios/CLAUDE.md` and `.claude/rules/ios-patient-mode.md` apply to the web client's patient mode as written (one thing per screen, no horizontal gestures, no pull-to-refresh, no badges, no autoplay, 20pt body, 56pt targets, 7:1 contrast, a spoken twin for every card).
- The backend gains a small deployment (container, one region) so the phone can reach it; fixture providers remain until real credentials exist.

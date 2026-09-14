# Checkpoints — where you can try the app yourself

Each checkpoint is a point where the pipeline stops being the only thing that can see the product. When a checkpoint is reached, the operator posts "Checkpoint N ready" with the exact steps, and `make checkpoint N=<n>` walks the backend part of it for you. Everything before CP7 runs on your Mac with no cloud account; nothing needs a real phone until CP8.

Statuses: `planned` → `ready` (you can run it) → `passed` (you ran it and it did what the criteria say).

| # | Name | You will see | Stories behind it | Status |
|---|------|--------------|-------------------|--------|
| 1 | Heartbeat | `make dev`, open http://127.0.0.1:8000/docs, call `GET /health` | scaffold | **ready** |
| 2 | Accounts, keys, consent, audit | Register by phone code (the code prints in the server log, no SMS), create a profile, issue a caregiver key scoped to `medicines, visits`, watch it read medicines and get refused on notes, then list the refusal in the audit trail | E00-01, E00-02, E00-07 | planned |
| 3 | Memory and State | Add a blood-pressure reading as a Fact with provenance, watch State recompute and record the trigger; a Fact without provenance is rejected | E00-03, E00-04 | planned |
| 4 | Three doors, proxy, claim | Set up a profile *for someone* by phone number, try to create a second one for the same number (refused), then claim it as the patient and see the steward key become the chief key with consent recorded | E01-01, E01-02 | planned |
| 5 | Paper in, facts out | Upload the sample lipid report from `backend/tests/fixtures/paper/`, get a review card with per-field confidence, confirm it, and see Facts with provenance appear on the timeline | E02-01, E02-07 | planned |
| 6 | Medicines | Add three drugs from a label, see the reconciliation (refill vs dose change), the interaction check, the running count and reorder date, and the medication story in plain words; a high-risk drug refuses a dose without a label photo | E04-01…E04-07, E16-04 | planned |
| 7 | Plain words and the visit loop | Paste a visit transcript, get a post-visit memo in the profile's language that passes the plain-words verifier; see a fragment example fail it | E22-01, E05-01…E05-06 | planned |
| 8 | Feed and WhatsApp (sandbox) | Call the feed endpoint and see the supply order (now, today, gate, story, learning); send a photo to the WhatsApp sandbox number and watch it file itself and reply | E21 backend, E19-01…E19-03 | planned |
| 9 | iOS Today on the simulator | Open `ios/Nura.xcodeproj`, run on iPhone simulator, sign in with a phone code, see the Today shell with the Now card and Taken, and the medium widget | Session 10 | planned |
| 10 | iOS feed and onboarding | Page the vertical feed, hear a card on tap, hit the gate card; run onboarding with the word cloud and read-back | Sessions 11–12 | planned |
| 11 | Your family on TestFlight | The app on your phone and your dad's, against the pilot backend in-region | build-plan §6, weeks 2–8 | planned |

## How a checkpoint is tested

- **Backend checkpoints (1–8)**: `make dev` in one terminal, `make checkpoint N=<n>` in another. The script runs the scenario against the local server with a fixture provider (no SMS, no real drug database, no WhatsApp) and prints each step with ✓ or ✗. The FastAPI page at `/docs` lets you repeat any step by hand.
- **iOS checkpoints (9–10)**: the operator runs the app on the simulator first and attaches screenshots to the checkpoint note; you then run it yourself from Xcode.
- **TestFlight (11)**: needs your Apple developer account; the operator prepares the build and the steps.

## Rules the operator follows between checkpoints

- Stories merge when CI is green, the safety and plain-words reviewers pass, and the operator has read the diff. `risk:high` stories get a written note in the PR saying what was checked.
- A checkpoint is not declared ready until `make checkpoint` passes end to end on a clean database.
- Anything that needs a real credential (SMS provider, licensed drug data, WhatsApp BSP, Apple) is a fixture until you say otherwise; the checkpoint says so where it applies.

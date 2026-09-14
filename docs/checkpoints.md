# Checkpoints — where you can try the app yourself

Each checkpoint is a point where the pipeline stops being the only thing that can see the product. When a checkpoint is reached, the operator posts "Checkpoint N ready" with the exact steps, and `make checkpoint N=<n>` walks the backend part of it for you. Everything before CP7 runs on your Mac with no cloud account; nothing needs a real phone until CP8.

Statuses: `planned` → `ready` (you can run it) → `passed` (you ran it and it did what the criteria say).

| # | Name | You will see | Stories behind it | Status |
|---|------|--------------|-------------------|--------|
| 1 | Heartbeat | `make dev`, open http://127.0.0.1:8000/docs, call `GET /health` | scaffold | **ready** |
| 2 | Accounts, keys, consent, audit | Register by phone code (the code prints in the server log, no SMS), create a profile, issue a caregiver key scoped to `medicines, visits`, watch it read medicines and get refused on notes, then list the refusal in the audit trail | E00-01, E00-02, E00-07 | **ready** |
| 3 | Memory and State | Add a blood-pressure reading as a Fact with provenance, watch State recompute and record the trigger; a Fact without provenance is rejected; a key without the record cannot read State | E00-03, E00-04 | **ready** |
| 4 | Three doors, proxy, claim | Set up a profile *for someone* by phone number, try to create a second one for the same number (refused, in words that name nobody), then claim it as the patient and see the steward key become the chief key with consent recorded | E01-01, E01-02 | **ready** |
| 5 | Paper in, facts out | Upload the sample lipid report from `backend/tests/fixtures/paper/`, get a review card with per-field confidence, confirm it, and see Facts with provenance appear on the timeline | E02-01, E02-07 | planned |
| 6 | Medicines | Add three drugs from a label, see the reconciliation (refill vs dose change), the interaction check, the running count and reorder date, and the medication story in plain words; a high-risk drug refuses a dose without a label photo | E04-01…E04-07, E16-04 | planned |
| 7 | Plain words and the visit loop | Paste a visit transcript, get a post-visit memo in the profile's language that passes the plain-words verifier; see a fragment example fail it | E22-01, E05-01…E05-06 | planned |
| 8 | Feed and WhatsApp (sandbox) | Call the feed endpoint and see the supply order (now, today, gate, story, learning); send a photo to the WhatsApp sandbox number and watch it file itself and reply | E21 backend, E19-01…E19-03 | planned |
| 9 | iOS Today on the simulator | Open `ios/Nura.xcodeproj`, run on iPhone simulator, sign in with a phone code, see the Today shell with the Now card and Taken, and the medium widget | Session 10 | planned |
| 10 | iOS feed and onboarding | Page the vertical feed, hear a card on tap, hit the gate card; run onboarding with the word cloud and read-back | Sessions 11–12 | planned |
| 11 | Your family on TestFlight | The app on your phone and your dad's, against the pilot backend in-region | build-plan §6, weeks 2–8 | planned |

## How a checkpoint is tested

- **Backend checkpoints (1–8)**: `make dev` in one terminal, `make checkpoint N=<n>` in another. The script runs the scenario against the local server with a fixture provider (no SMS, no real drug database, no WhatsApp) and prints each step with ✓ or ✗; it stops at the first ✗. The FastAPI page at `/docs` lets you repeat any step by hand. `make dev` also writes its log to `backend/.dev.log` (ignored by git), which is where the script reads the login codes from; `make reset-db` gives you a clean local database (stop `make dev` first).
- **iOS checkpoints (9–10)**: the operator runs the app on the simulator first and attaches screenshots to the checkpoint note; you then run it yourself from Xcode.
- **TestFlight (11)**: needs your Apple developer account; the operator prepares the build and the steps.

## How to run checkpoint 2

Two terminals, both at the top of the repo. Every `make` target uses `python3`, the Python 3.12 on your Mac; the first time, `make setup` installs the backend into it.

```sh
make setup              # once: python3 -m pip install -e "backend[dev]"
make dev                # terminal 1: migrates dev.db, serves on http://127.0.0.1:8000, log also goes to backend/.dev.log
make checkpoint N=2     # terminal 2: walks the whole scenario, about two seconds
```

The script registers two fresh phone numbers every run (the last four digits are random), so you can run it as often as you like on the same `dev.db`. Nothing is sent anywhere: the "SMS" is a line in the server log, and the script reads the six digits from `backend/.dev.log` the way you would read them off the screen. If the server is not running, or was started some other way than `make dev`, the first line is a ✗ that says so.

What you will see (the phone numbers and times change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591113897) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa's account has no profile yet (GET /me)
✓ opening a profile on stale wording (version 0) was refused: NotTheCurrentWording (400), nothing opened
✓ Pa opened his own profile (wording 1, in Malay, in the app), agreeing to Nura keeping his record; as its owner he needs no key and every part is open to him
✓ Pa wrote a private note (scope notes: open to its owner, not to a caregiver key)
✓ Mei (+6592223329) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ a caregiver key for Mei before Pa agreed to share was refused: ConsentWithheld (403)
✓ Pa agreed to let Mei, his daughter, see his medicines and visits; the words he read:
    You are letting Mei, daughter, see some of your record.
    Mei can see these parts:
    - your medicines
    - your visits to the doctor
    Mei can see them until you say stop.
    You can stop this at any time.
✓ Pa cut Mei a caregiver key: medicines and visits (and whose profile it is), for thirty days, resting on that consent
✓ Mei opens Pa's profile with her key: his name and language, as caregiver
✓ Mei reads Pa's medicines: allowed, and none are recorded yet ([])
✓ Mei reads Pa's notes: refused, OutOfScope notes (403); the note itself never left
✓ Mei reads Pa's consents: refused, OutOfScope family (403); only Pa or his chief may
✓ Pa lists his consents: hold_health_record and share_with_family (naming Mei), both in force
✓ Pa lists the keys cut on his profile: caregiver (he holds none: it is his)
✓ Pa reads his audit trail (15 lines, newest first); the refusals are on it:
    2026-09-14T07:51:18  Mei  read family consent  refused OutOfScope
    2026-09-14T07:51:18  Mei  read notes note  refused OutOfScope
    2026-09-14T07:51:18   Pa  read family consent  refused ConsentWithheld
✓ Pa revoked Mei's key
✓ Mei's next read is refused: NoKey (403), medicines included
✓ that reach is on Pa's trail: the newest line is Mei's refused read, NoKey
✓ a read with no token is refused: NoSession (401)
✓ Mei signed out (204); her token is refused from then on: NoSession (401)
checkpoint 2 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 2 passed`. That is the whole of the criteria for this checkpoint: a person can register with a code that never travels over the API; a profile opens only on today's consent wording; a key cannot be cut for someone until the patient has agreed, in words he read, to let that person in; the key opens exactly the parts it names and nothing else; the patient can see every agreement, every key and every reach — including the refused ones — and closing a key stops the holder at once, with that too on the trail. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, using the profile id and Mei's token from it — or register your own two numbers there the same way (`POST /auth/phone/start`, read the code from the `make dev` terminal, `POST /auth/phone/verify`; press *Authorize* at the top of the page and paste the token):

1. **The refused notes read.** As the caregiver (Mei's token), call `GET /profiles/{profile_id}/notes`. You get `403 {"refusal": "OutOfScope", "scope": "notes"}` and nothing of the note. Then, as Pa, call `GET /profiles/{profile_id}/audit` and find that read near the top: `outcome: refused`, `refused_because: OutOfScope`, with Mei's `actor_person_id` and no note text anywhere on the line.
2. **Revoking a key.** As Pa, `GET /profiles/{profile_id}/keys` to see the caregiver key and its `key_id`, then `DELETE /profiles/{profile_id}/keys/{key_id}`. The answer shows `revoked_at` set. Any call Mei makes after that — even `GET /profiles/{profile_id}/medicines`, which worked a moment ago — is `403 {"refusal": "NoKey"}`, and it appears as the newest line of Pa's trail.

To start again from nothing: stop `make dev` (Ctrl-C), run `make reset-db`, then `make dev` again.

## How to run checkpoint 3

Same two terminals as checkpoint 2, from the top of the repo. It runs on the same `dev.db`; nothing from checkpoint 2 is needed first.

```sh
make dev                # terminal 1, if it is not already running
make checkpoint N=3     # terminal 2: about two seconds
```

What you will see (the phone numbers, ids and times change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591114464) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Pa reads his State (GET /profiles/{id}/state): snapshot 1, trigger first, posture stable, all six dimensions computed and empty — clinical, functional, cognitive, situational, preference, family
✓ Pa added a blood-pressure reading, 138/84 (POST /profiles/{id}/readings): one event (a reading, taken now, in the app) and one fact, blood_pressure.reading, that names it
✓ State recomputed as the fact landed: snapshot 2 supersedes snapshot 1, and records its trigger — new_fact, naming fact 3d3ae95b…
✓ the reading is in the clinical dimension with its provenance (the event it came from, confirmed by Pa); the posture stays stable — 138/84 is a number State holds, not a number State judges
✓ Pa added a second reading, 142/88: snapshot 3 supersedes snapshot 2 and names the new fact; snapshots are rows that are never edited
✓ reading State again with nothing new returns the same snapshot: no recompute for the same facts
✓ every fact in State names the event or artefact it came from; the readings route writes the event first and the fact names it, so no request can ask for a fact with no provenance — that refusal (NoProvenance, 400) is held at the service and proven in backend/tests/test_memory_acceptance.py
✓ Mei (+6592222911) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa agreed to let Mei, his daughter, see his readings and his record (not his notes)
✓ Pa cut Mei a caregiver key to the readings only; with it State is refused: OutOfScope records (403) — a snapshot is the record folded, so it is read under the record's scope
✓ Pa re-cut the key to readings and records; Mei reads State: the clinical dimension with the reading in it; situational, preference and family withheld by name (her key covers no visits, notes or family), and she is told it was not checked against the record
✓ Mei reads Pa's notes: refused, OutOfScope notes (403)
✓ Pa reads his audit trail (69 lines); Mei's refused reaches are on it:
    2026-09-14T08:28:01  Mei  read notes note  refused OutOfScope
    2026-09-14T08:28:01  Mei  read records state_snapshot  refused OutOfScope
checkpoint 3 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 3 passed`. That is the whole of the criteria: a profile has a State before it has a fact, in all six dimensions; a reading becomes an event and a fact that names it, and State recomputes as the fact lands, writing a new snapshot that supersedes the last and records what triggered it — the fact, by id; a number on its own never moves the posture; the same facts read again are the same snapshot; nothing the API offers can write a fact without provenance; a key that does not cover the record cannot read State, and that reach is on the owner's trail; a key that does reads State narrowed to what it covers, with what it does not cover named. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token (press *Authorize* and paste it) and the profile id from it:

1. **Watch a snapshot supersede the last.** Call `GET /profiles/{profile_id}/state` and note `state_id` and `sequence`. Then `POST /profiles/{profile_id}/readings` with `{"systolic": 130, "diastolic": 80}`, and call `GET /profiles/{profile_id}/state` again: `sequence` is one higher, `supersedes_id` is the `state_id` you noted, and `trigger` is `{"kind": "new_fact", "fact_id": …}` with the `fact_id` the POST answered with. Under `dimensions.clinical.facts.blood_pressure.reading` the value is what you typed and `event_id` is the event the POST answered with.
2. **Read State with Mei's key.** As Mei (her token), call `GET /profiles/{profile_id}/state`: `dimensions.situational`, `.preference` and `.family` are `null`, `withheld` names them and the scopes she does not hold, and `stale` is `null` — her key cannot check the record against the snapshot, so she is told so rather than shown a freshness she could not verify. Then, as Pa, `GET /profiles/{profile_id}/audit?actor_person_id=<Mei's person_id>` shows her reads of `state_snapshot` as `allowed` under `records`, and the one with the readings-only key as `refused`.

The fact without provenance is refused at the service, not over HTTP: the readings route always writes the event before the fact and has no field that could leave the fact resting on nothing, so there is no "deliberately bad request" to send. The refusal (`NoProvenance`, which the API would answer with 400) and the table's own check constraint are both proven in `backend/tests/test_memory_acceptance.py`.

## How to run checkpoint 4

The same two terminals as checkpoint 2; it does not depend on checkpoint 3 having been run.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0007 adds the stewardship), serves on http://127.0.0.1:8000
make checkpoint N=4     # terminal 2: walks the whole scenario, about two seconds
```

Three fresh phone numbers every run — Mei, Pa's son Kit, and Pa — so it can be run again on the same `dev.db`. Nothing is sent anywhere: the "SMS" is a line in the server log, and the claim message Pa would get on WhatsApp is not sent yet (E19); here Pa registers with his number and finds the profile waiting.

What you will see (the numbers and times change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Mei (+6594441735) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Mei set up a profile for Pa (+6593339435) on the basis that he asked: she is its steward, holding a chief key over everything but his private notes
✓ Mei's doors (GET /doors): no profile of her own, one she is stewarding — Pa's
✓ Kit (+6595557844) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Kit (+6595557844) tried the same number and was refused: AlreadySetUp (409), the answer naming nobody — {"refusal":"AlreadySetUp"}; Mei trying again got the very same words
✓ as steward Mei reads the medicines (none yet), records a blood-pressure reading for Pa, 138/84 (one event, one fact resting on it, under the agreement she gave for him), reads the stewardship (open, basis patient_asked) and the trail (26 lines); the private notes refuse her: OutOfScope notes (403)
✓ Pa (+6593339435) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa registered; opening his own profile beside the one waiting was refused: WaitingToBeClaimed (409)
✓ Pa sees the profile waiting for him (GET /profiles/mine/claimable): set up by Mei, daughter, who would keep seeing 9 parts; the words he reads, in Malay:
    Nura menyimpan surat-surat anda, ubat anda dan buku tekanan darah anda.
    Semuanya kekal di Singapura.
    Anda boleh minta Nura berhenti pada bila-bila masa.
    Selepas itu, Nura tidak menyimpan apa-apa yang baru.
    Apa yang sudah disimpan kekal dalam rekod anda.
    Anda membenarkan Mei, daughter, melihat sebahagian daripada rekod anda.
    Mei boleh melihat bahagian ini:
    - ubat anda
    - lawatan anda ke doktor
    - buku tekanan darah dan bacaan gula anda
    - surat-surat anda
    - surat insurans anda
    - kad kecemasan anda
    - senarai keluarga anda
    - soalan anda kepada Nura
    - mesej yang Nura hantar
    Mei boleh melihatnya sehingga anda minta ia dihentikan.
    Anda boleh berhenti pada bila-bila masa.
✓ Pa minted his OK (a confirmation for subject claim, good for ten minutes, used once) and claimed the profile: he is its owner
✓ claiming again is refused: NotTheClaimant (403); there is nothing left to claim
✓ Pa reads his consents: Mei's agreement for him (patient_asked) withdrawn by him at the claim; his own agreement to Nura keeping his record, in Malay; and his agreement to let Mei, his daughter, see the parts she held — on his own basis
✓ Pa reads his keys: the steward key is closed; Mei now holds a chief key, cut by Pa, resting on that consent
✓ the stewardship is closed, naming Pa as the person who claimed
✓ Pa reads his trail (50 lines): the claim is on it in his name — the transfer, the consents, the key, the closed stewardship — and the refusals:
    2026-09-14T08:36:01   Pa  write profile profile  refused NotTheClaimant
    2026-09-14T08:36:01  Mei  read notes note  refused OutOfScope
    2026-09-14T08:36:01  Mei  write profile profile  refused AlreadySetUp
✓ Kit's try is not on the trail: a stranger's reach is counted out of band, never written in, so nobody can fill a trail by repeating a number
✓ Mei opens Pa's profile as his chief on his consent, reads his medicines, and cannot read his private notes: OutOfScope notes (403); her doors now list Pa's profile as one she was let in to
✓ Kit trying the number once more, now that Pa owns the profile, gets the same words as before: nothing says which case it is
checkpoint 4 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 4 passed`. The criteria: a person can set up a profile for someone else by that person's number and hold it as its steward — a chief key over everything but the private notes, and the agreement to keeping the record given on the patient's behalf on a declared basis; one profile per number, ever — a second person is refused in the same words whoever holds the first, and the answer names nobody; the patient, registering with that number, is shown who set it up, what they would keep seeing and the words in his language, and only his own OK (a confirmation he minted, used once) claims it; the claim transfers ownership, withdraws the steward's agreement and records his own, records his agreement to let the steward in, cuts the steward a chief key resting on it and closes the stewardship, every step on the trail he can read; and the steward, now his chief, still cannot read his private notes. If you see a ✗, the line says what was asked, what came back and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run:

1. **The claimant's view.** Register a fourth number (`POST /auth/phone/start`, read the code from the `make dev` terminal, `POST /auth/phone/verify`), then as Mei call `POST /profiles/for-someone` with that number and `"basis": "patient_asked"`. As the new person, `GET /doors`: the profile is under `claimable`, with `set_up_by`, `parts` and the words. `GET /profiles/{profile_id}` answers with `standing: claimant` and `scopes: ["profile"]`; `GET /profiles/{profile_id}/medicines` is `403 {"refusal": "OutOfScope", "scope": "medicines"}` — until he claims, he sees whose profile it is and nothing else.
2. **A yes for other words.** As that person, `POST /profiles/{profile_id}/confirmations` with `{"subject": "claim", "language": "en"}`, then `POST /profiles/{profile_id}/claim` with that `confirmation_id` and `"language": "ms"`. The answer is `400 {"refusal": "NotWhatWasConfirmed"}`: the yes was for the English words, not the Malay ones. Claim again with `"language": "en"` and it goes through; the refusal is on the trail (`GET /profiles/{profile_id}/audit`) as `refused_because: NotWhatWasConfirmed`.

## Rules the operator follows between checkpoints

- Stories merge when CI is green, the safety and plain-words reviewers pass, and the operator has read the diff. `risk:high` stories get a written note in the PR saying what was checked.
- A checkpoint is not declared ready until `make checkpoint` passes end to end on a clean database.
- Anything that needs a real credential (SMS provider, licensed drug data, WhatsApp BSP, Apple) is a fixture until you say otherwise; the checkpoint says so where it applies.

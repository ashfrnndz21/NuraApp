# Checkpoints — where you can try the app yourself

Each checkpoint is a point where the pipeline stops being the only thing that can see the product. When a checkpoint is reached, the operator posts "Checkpoint N ready" with the exact steps, and `make checkpoint N=<n>` walks the backend part of it for you. Everything before CP7 runs on your Mac with no cloud account; nothing needs a real phone until CP9.

Statuses: `planned` → `ready` (you can run it) → `passed` (you ran it and it did what the criteria say).

| # | Name | You will see | Stories behind it | Status |
|---|------|--------------|-------------------|--------|
| 1 | Heartbeat | `make dev`, open http://127.0.0.1:8000/docs, call `GET /health` | scaffold | **ready** |
| 2 | Accounts, keys, consent, audit | Register by phone code (the code prints in the server log, no SMS), create a profile, issue a caregiver key scoped to `medicines, visits`, watch it read medicines and get refused on notes, then list the refusal in the audit trail | E00-01, E00-02, E00-07 | **ready** |
| 3 | Memory and State | Add a blood-pressure reading as a Fact with provenance, watch State recompute and record the trigger; a Fact without provenance is rejected; a key without the record cannot read State | E00-03, E00-04 | **ready** |
| 4 | Three doors, proxy, claim | Set up a profile *for someone* by phone number, try to create a second one for the same number (refused, in words that name nobody), then claim it as the patient and see the steward key become the chief key with consent recorded | E01-01, E01-02 | **ready** |
| 5 | Paper in, facts out | Upload the sample lipid report from `backend/tests/fixtures/paper/`, get a review card with per-field confidence (the unsure fields dotted), correct one value, confirm with one OK, and see Facts with provenance appear; upload the warfarin label and see the high-risk class on the card; a key without the record cannot see a card | E02-01, E02-07, E16-04 | **ready** |
| 6 | Medicines | Add three drugs from a label, see the reconciliation (refill vs dose change), the interaction check, the running count and reorder date, and the medication story in plain words; a high-risk drug refuses a dose without a label photo | E04-01…E04-07, E16-04 | **ready** |
| 7 | Plain words and the visit loop | Paste a visit transcript, get a post-visit memo in the profile's language that passes the plain-words verifier; see a fragment example fail it | E22-01, E05-01…E05-06 | planned |
| 8 | Feed (backend) | Call the feed endpoint and see the supply order (now, today, gate, story, learning) with why-am-I-seeing-this on every card; page twice with the cursor; a burst of readings is capped; quiet hours hold everything but a red flag, which jumps the queue; "Not for me" holds that kind of card for the day; Mei sees the caregiver supply; a learning card from an allowlisted source appears after the self-search job runs; a medicine running low makes a reorder card from E04's count | E21 backend (Session 8) | **ready** |
| 9 | WhatsApp (sandbox) | Mei forwards a photo to the number and it files itself as a review card and replies; she posts "BP 150/90" and gets a read-back that only her own "yes" turns into a Fact; a stranger's number gets one fixed line and nothing is stored; "he fell" writes a Flag first and escalates in-thread; the morning card goes to Pa as an approved template and his "tired" is written down; the thread is by reference and every line is on the trail | E19-01…E19-03, E19-05 | **ready** |
| 10 | Today on your phone (web) | Open the app URL in Safari on your iPhone, add it to the home screen, sign in with a phone code, see the Today shell with the Now card and Taken; it opens offline | W1 (ADR 0001) | **ready** |
| 11 | Onboarding on your phone (web) | Run onboarding with the word cloud and read-back | W2–W3 (ADR 0001) | planned |
| 12 | Feed on your phone (web) | Page the vertical feed, hear a card on tap, hit the gate card | W2–W3 (ADR 0001) | planned |
| 13 | Family, roster and Dad's trail | Mei adds Siti as a helper and narrows her to the medicines; widening is refused; Pa marks his notes "only me" and Mei's next read is refused and on his trail in his words; the roster (Mei weekdays, Kit weekends) and a task only Siti can tap done; the family thread with a message and a reading card; Kit's digest; a message to Pa previewed in Malay and scheduled; the LPA uploaded and shown backing the stewardship | E12-01, E12-02, E12-03, E12-04, E12-06, E12-09 | **ready** |
| 14 | Emergency card and not feeling well | Written by its story (E13/E14) | E13, E14 | planned |
| 15 | Biography | Written by its story | — | planned |
| 16 | Timeline | Written by its story | — | planned |
| 17 | Trends, routine and calendar | Written by its story | — | planned |
| 18 | Capture | Written by its story | — | planned |
| 19 | Your family on TestFlight | The app on your phone and your dad's, against the pilot backend in-region | build-plan §6, weeks 2–8 | planned |

**Trust documents.** Not checkpoints, but read before CP7 and CP19: `docs/trust/` holds the SaMD boundary review (signed off before any flag ships), the recording consent pattern (counsel's sign-off before a visit is recorded on a real profile) and the PDPA data map, breach runbook and DPO (the tabletop is owed before CP19). E16.

## How a checkpoint is tested

- **Backend checkpoints (1–9, 13)**: `make dev` in one terminal, `make checkpoint N=<n>` in another. The script runs the scenario against the local server with a fixture provider (no SMS, no real drug database, no WhatsApp) and prints each step with ✓ or ✗; it stops at the first ✗. The FastAPI page at `/docs` lets you repeat any step by hand. `make dev` also writes its log to `backend/.dev.log` (ignored by git), which is where the script reads the login codes from; `make reset-db` gives you a clean local database (stop `make dev` first).
- **Web checkpoints (10–12, ADR 0001)**: `make dev` and `make web` in two terminals, then the app in a browser — on the Mac at http://127.0.0.1:5173, on the phone at the Mac's address on the same Wi-Fi. The operator walks it first with Playwright (`make web-e2e`) and attaches screenshots to the checkpoint note; you then walk it yourself by hand.
- **TestFlight (19, last)**: needs your Apple developer account; the operator prepares the build and the steps.

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

## How to run checkpoint 5

The same two terminals as checkpoint 2; it does not depend on any earlier checkpoint having been run.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0008 adds the review card), serves on http://127.0.0.1:8000
make checkpoint N=5     # terminal 2: walks the whole scenario, about three seconds
```

Two fresh phone numbers every run, Pa and Mei, so it can be run again on the same `dev.db`. No photo is sent: the two papers in `backend/tests/fixtures/paper/` are redacted samples whose image is not committed — each is a small placeholder byte string the script generates, and a JSON file that says what the extractor reads off it. The bytes go to the local object store under `backend/var/objects/SG/` (ignored by git); the real OCR and vision extractor is a later adapter behind the same interface, and the fixture one answers by the digest of the bytes it is shown.

What you will see (the numbers, ids and times change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591115168) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Pa uploaded the lipid report (POST /profiles/{id}/photos, the redacted sample's placeholder bytes): stored in the SG object store as artefact 00439a69…, read as a lab_report dated 2023-09-07, and answered with a review card — seven fields, each with its confidence; the two below 0.8 are dotted:
    total_cholesterol    230                              mg/dL   confidence 0.97  clear
    hdl                  73                               mg/dL   confidence 0.95  clear
    ldl                  152                              mg/dL   confidence 0.71  dotted — needs your eye
    triglycerides        64                               mg/dL   confidence 0.52  dotted — needs your eye
    vldl                 10.78                            mg/dL   confidence 0.90  clear
    tc_hdl_ratio         3.1                                      confidence 0.93  clear
    non_hdl_cholesterol  156.3                            mg/dL   confidence 0.88  clear
✓ nothing is a fact yet: GET /profiles/{id}/facts?subject=lipid_panel is [] until he says so
✓ Pa corrected triglycerides from 64 to 54 (the paper says 54) and minted his OK; the same OK offered for a different correction (45) was refused: NotWhatWasConfirmed (400) — the yes binds to the decisions as shown
✓ one tap saved the card: seven facts, each naming the photo as provenance, confirmed_by_person Pa, with unit, valid from 7 September 2023 on his clock (2023-09-06T16:00Z):
    hdl                  73 mg/dL  ← artefact 00439a69…  by Pa
    ldl                  152 mg/dL  ← artefact 00439a69…  by Pa
    non_hdl_cholesterol  156.3 mg/dL  ← artefact 00439a69…  by Pa
    tc_hdl_ratio         3.1  ← artefact 00439a69…  by Pa
    total_cholesterol    230 mg/dL  ← artefact 00439a69…  by Pa
    triglycerides        54 mg/dL  ← artefact 00439a69…  by Pa
    vldl                 10.78 mg/dL  ← artefact 00439a69…  by Pa
✓ confirming the card again is refused: AlreadyConfirmed (409); its facts are facts now
✓ the facts read back (GET /profiles/{id}/facts?subject=lipid_panel, 7); State recomputed as each landed — snapshot 7, trigger new_fact naming fact c60c61f7…; the clinical dimension holds the lipid panel with the corrected 54
✓ Pa uploaded the warfarin label: read as a medicine_label dated 2024-03-12, the dose line parsed from Malay ("1 biji sekali sehari waktu malam"), and the card marked high_risk_class anticoagulant — looked up from the safety table, not proposed by the extractor and not his to reject:
    name                 Warfarin                                 confidence 0.96  clear
    strength             5                                mg      confidence 0.93  clear
    dose                 1 tablet once a day at night     tablet  confidence 0.74  dotted — needs your eye
    quantity             28                               tablets confidence 0.88  clear
    dispensed_at         2024-03-12                               confidence 0.90  clear
    prescriber           Dr Lim                                   confidence 0.61  dotted — needs your eye
✓ Pa rejected the unclear prescriber and confirmed the rest: five medicine facts under the medicines scope, the dose naming its drug and resting on the label photo; the rejected field wrote nothing
✓ GET /profiles/{id}/facts?subject=medicine now lists the label's facts (subject medicine → scope medicines); the reconciled list at GET /profiles/{id}/medicines is checkpoint 6
✓ the high-risk label rule (E16-04): a warfarin dose fact whose provenance is not a PHOTO artefact is refused, HighRiskNeedsLabelPhoto (400), and written to the trail. No route can express it — the only way to write a medicine dose over HTTP is a card from a photo — so the refusal is held at the service (app/safety/high_risk.py, a hook on before_fact_write) and proven in backend/tests/test_high_risk.py from a WhatsApp message, a PDF and a screenshot
✓ Mei (+6592220898) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa cut Mei a caregiver key to the readings only; the review cards refuse her: OutOfScope records (403)
✓ Pa re-cut the key to readings and records; Mei reads both cards, each closed and naming Pa as its confirmer
✓ the label's facts are under the medicines scope: Mei's key to the record does not open them, OutOfScope medicines (403)
✓ Pa reads his audit trail (245 lines): the photos, the cards, every field, every fact and every yes are on it as writes, and so are the refusals:
    2026-09-14T09:25:56  Mei  read medicines fact  refused OutOfScope
    2026-09-14T09:25:56  Mei  read records review_card  refused OutOfScope
    2026-09-14T09:25:56   Pa  read records review_card  refused AlreadyConfirmed
    2026-09-14T09:25:56   Pa  write records review_card  refused NotWhatWasConfirmed
checkpoint 5 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 5 passed`. The criteria: a photo's bytes go to the object store of the profile's region and the row holds only a key and a digest; the extractor's answer is a review card, never a fact — every field with its confidence, and the ones below the threshold dotted for the person's eye; a correction is kept beside the proposal it does not overwrite; one OK saves the whole card, and it binds to the decisions as shown, so a decision changed after it was minted is refused; every fact the card writes names the photo as its provenance, the person as its confirmer and the unit, and is valid from the date on the paper; a rejected field writes nothing; a card is confirmed once; State recomputes as each fact lands and names its trigger; the label card shows the high-risk class from the safety table, and a high-risk dose can only ever rest on a label photo, whichever surface writes it; the label's facts sit under the medicines scope, the cards under the record's, and a key that covers neither is refused and written down. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token (press *Authorize* and paste it) and the profile id from it:

1. **A page the extractor cannot read.** `POST /profiles/{profile_id}/photos` with `"content_type": "image/png"`, any `captured_at`, and `"data"` set to the base64 of a few bytes of your own (`printf 'hello' | base64`). The answer is `201` with a card whose `document_kind` is `unknown` and whose `fields` are `[]`: nothing was guessed. Try again with `"content_type": "application/pdf"` and the answer is `400 {"refusal": "NotAPhoto"}`.
2. **The yes is the confirmer's own.** Take an open card's `card_id` (upload the lipid report again: the same bytes make a new card), mint an OK as Pa with `POST /profiles/{profile_id}/confirmations` and `{"subject": "review_card", "card_id": …, "decisions": [{"field_id": …, "decision": "confirmed"}, …]}` naming every field. Then, as Mei (her token, with the key to `readings` and `records` the run cut her), call `POST /profiles/{profile_id}/review-cards/{card_id}/confirm` with those decisions and Pa's `confirmation_id`: `403 {"refusal": "NotAConfirmerHere"}` — a yes is spent only by the person who said it. As Pa, the same call goes through, and `GET /profiles/{profile_id}/audit?scope=records&limit=500` shows Mei's refused write of `review_card` beside it.

The high-risk refusal is at the service, not over HTTP: the only way to write a medicine dose over the API is a card made from a photo, so there is no request that could offer a WhatsApp message or a PDF as the provenance of a warfarin dose. The rule (`HighRiskNeedsLabelPhoto`, which the API would answer with 400) lives in `backend/app/safety/high_risk.py` as a hook the memory store runs before any fact is written, and is proven from a message, a PDF and a screenshot in `backend/tests/test_high_risk.py`.

## How to run checkpoint 6

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having been run. The drug data is the fixture register in `backend/tests/fixtures/drugs/registry.json` (a dozen medicines common in Malaysia and Singapore, with NPRA- and HSA-shaped numbers that are not real ones); no licensed database is called, and no model writes a sentence.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0009 adds the medicine tables), serves on http://127.0.0.1:8000
make checkpoint N=6     # terminal 2: walks the whole scenario, about three seconds
```

Two fresh phone numbers every run — Pa and Mei, his helper — so it can be run again on the same `dev.db`. Each "label photo" is a few placeholder bytes sent through `POST /profiles/{id}/photos` (checkpoint 5's route): the fixture extractor knows nothing about them, so the review card comes back `unknown` with no fields, and the artefact — a photo, stored under `backend/var/objects/SG/` — is what the label names as its source. The label's own fields are typed in this checkpoint; reading them off the photo is the extractor's job (E02) and the two meet at the artefact id.

What you will see (the numbers, ids and dates change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591110353) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Pa reads his medicines (GET /profiles/{id}/medicines): none yet ([])
✓ Pa kept a label photo (POST /profiles/{id}/photos: stored in the region's object store, an artefact of kind photo; the extractor read nothing off it, so no card to confirm) and asked what the label means (POST /profiles/{id}/medicines/draft): a new line — the fixture register identified Norvasc 5 mg as amlodipine (MAL19970001A), the dose read from the label's Malay words, 1 biji sekali sehari pagi; nothing written yet
✓ Pa said OK (POST /profiles/{id}/confirmations, subject medicine: a yes for exactly this label, good for ten minutes, used once) and added it (POST /profiles/{id}/medicines): one medication fact on the photo, confirmed by him, one line, one supply of 30
✓ Pa reads the story in Malay (GET .../story; his profile's language): purpose, how to take, what to look out for, what to avoid, if he forgot, and the boundary — from templates keyed by the licensed monograph, no model, the chemical name kept small:
    Ini ubat tekanan darah anda.
    Ia menjaga tekanan darah anda supaya tidak tinggi.
    Ambil 1 biji sekali sehari.
    Ambil bersama sarapan.
    Makan atau tidak, tidak mengapa untuk ubat ini.
    Jika buku lali anda bengkak, beritahu Dr Tan.
    Jika anda pening semasa berdiri, duduk dahulu.
    Kemudian beritahu Dr Tan.
    Limau gedang tidak sesuai dengan ubat tekanan darah anda.
    Jika anda terlupa, ambil apabila anda teringat.
    Jika yang seterusnya sudah dekat, tunggu yang seterusnya.
    Jangan sekali-kali ambil dua serentak.
    Ini membantu anda ambil apa yang Dr Tan beri.
    Tanya Dr Tan atau ahli farmasi sebelum anda ubah apa-apa.
✓ Pa tapped Taken twice (POST .../taken: his own tap, no confirm, a DOSE_TAKEN event each): 30 dispensed − 2 taken = 28 left, about 28 days; reorder on 2026-10-09 (days left − 3 days lead time for a retail pharmacy); in his words:
    You have 28 tablets of your blood pressure tablet left.
    That is about 28 days.
✓ warfarin: the register marks its class, anticoagulant, high-risk; from the label photo it was added (201), marked high_risk. Without a label photo it is refused by class — HighRiskNeedsLabelPhoto (400, the body names the class) — at the medicines service and again as the hook on the memory store; no route can offer a voice note or a PDF as a medicine's source (POST /photos takes only photos), so that refusal is proven in backend/tests/test_medicines.py and test_medicines_api.py from a voice note and a PDF
✓ aspirin was screened before it was saved: the licensed data flagged aspirin with warfarin, major (bleeding_risk), shown on the draft and written as a flag with the line; GET .../medicines/interactions renders it as a question for the doctor, both medicines named in his words:
    Ask Dr Tan about taking the aspirin and the blood thinner tablet together.
    Together they can make you bleed more easily.
✓ the new pack says 10 mg: the draft classifies it as a dose_change on the 5 mg line; written without his OK it is refused, NotAConfirmerHere (400), and the 5 mg line stays current
✓ with his OK the 10 mg line supersedes the 5 mg line (kept, marked with when, in GET .../medicines/history); the story does not tell him an amount — it asks the doctor:
    Your new pack says a different amount from before.
    Ask Dr Tan about the new amount.
✓ Pa reads today's doses (GET .../medicines/today): one card per medicine at its anchor:
    breakfast  Take 1 tablet of your blood pressure tablet with breakfast.  [Taken: taken]
    breakfast  Take 1 tablet of the aspirin with breakfast.  [Taken: not yet]
          bed  Take 1 tablet of the blood thinner tablet before bed.  [Taken: not yet]
✓ Mei (+6592223326) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Mei (helper key, medicines) reads the list (3 lines) and the warfarin story in Pa's language, and taps Taken for him in her own name; asking what a label means, minting a yes and adding a line are all refused: NotTheirsToChange (403) — a key to read the medicines is not a key to change them
✓ Pa reads his trail under the medicines scope (125 lines for the two of them); every refusal is on it by name, and no line says which medicine:
    2026-09-14T09:58:09   Pa  write medicines fact  refused NotAConfirmerHere
    2026-09-14T09:58:09  Mei  write medicines medication_line  refused NotTheirsToChange
    2026-09-14T09:58:09  Mei  read medicines medication_line  refused NotTheirsToChange
checkpoint 6 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 6 passed`. The criteria: a medicine is identified through the licensed data port and never guessed — the register's product, class and registration number, the dose read from the label's own words in Malay or English; nothing is written until the person says yes to exactly that label (a yes for anything else, or no yes, is refused and the list does not move); the story comes from templates keyed by the licensed monograph in his language, with the chemical name kept out of every sentence and no sentence telling him to start, stop or change anything; his taps bring the count down and the reorder date is arithmetic over what was dispensed, what was taken and the lead time of where it came from; a high-risk medicine (warfarin, insulin, digoxin, methotrexate, opioids — by class) is refused from anything but a label photo, by class name, at the service and again as the one hook on the memory store (`HighRiskNeedsLabelPhoto`, shared with checkpoint 5's card) — over HTTP every artefact is a photo, so that refusal is proven in the tests from a voice note and a PDF; a new medicine is screened against the list before it is saved and every flag names both medicines with a severity and reads as a question for the doctor; a dose change supersedes the old line only with his OK, keeps the old line in the history, and renders as a question for the doctor rather than a new amount; a helper's key reads the list and the story and taps Taken, and cannot add or change a line; every refusal is on the trail by name and nothing on the trail says which medicine. If you see a ✗, the line says what was asked, what came back and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token (press *Authorize* and paste it) and the profile id from it:

1. **A refill.** `POST /profiles/{profile_id}/photos` with any base64 bytes you like as `data`, `"content_type": "image/png"` and a `captured_at` (the card comes back `unknown`; keep its `artifact_id`), then `POST /profiles/{profile_id}/medicines/draft` with the warfarin label from the run — `{"generic": "warfarin", "strength": "3 mg", "dose_text": "1 tab ON", "quantity": 28}` — and the new `source_artifact_id`. The answer says `outcome: refill` and names the line. `POST /profiles/{profile_id}/confirmations` with `{"subject": "medicine", "label": …, "source_artifact_id": …}`, then `POST /profiles/{profile_id}/medicines` with the same label, artefact and the `confirmation_id`: a `supply` of 28 lands on the same line, and `GET /profiles/{profile_id}/medicines` shows the count gone up by 28.
2. **A yes for other words.** Mint a confirmation for a label of `"quantity": 28` and spend it on a `POST /profiles/{profile_id}/medicines` whose label says `"quantity": 30`. The answer is `400 {"refusal": "NotWhatWasConfirmed"}`: the yes was for a different label. Nothing is written, and the refusal is on the trail (`GET /profiles/{profile_id}/audit?scope=medicines`) as `refused_because: NotWhatWasConfirmed`.

## How to run checkpoint 8

The same two terminals as checkpoint 2; it does not depend on any earlier checkpoint having been run.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0010_feed adds the feed tables), serves on http://127.0.0.1:8000
make checkpoint N=8     # terminal 2: walks the whole scenario, about five seconds
```

Two fresh phone numbers every run, Pa and Mei. No model and no web call is made: the feed's two
ports — the searcher that finds pages and the compressor that turns a page into the lines a card
says — answer from `backend/tests/fixtures/feed/` (`NURA_FEED_FIXTURES`, which `make dev` sets), the
way the paper extractor does. The real fetcher and the grounded model call are later adapters behind
the same two ports. Pa is set up in English here so every line can be read on the terminal; the same
cards come in Malay and Chinese for a profile in those languages. He has a warfarin label from
checkpoint 5 and an amlodipine line added the checkpoint-6 way, five tablets at one a day, so the
medicines module's own count puts a reorder card on the feed.

The feed is the patient's on the owner's key and the caregiver's list on any other key. Two rules the
script leans on are dev-run only: `?at=` on `GET /profiles/{id}/feed` pretends it is another hour
(the quiet-hours step pretends 22:30; every other step pretends 10 in the morning, so the checkpoint
passes whatever the hour you run it at), and it is refused (`NotOnADevRun`, 400) on any deployment
that is not started with `NURA_DEV_CODE_SENDER=1`.

What you will see (the numbers, ids and times change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591118751) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Pa added three blood pressures (POST /profiles/{id}/readings): 146/90 a week ago, 142/88 three days ago, 138/84 today — each an event and a fact, State recomputing as they land
✓ Pa uploaded the warfarin label and confirmed the card (the checkpoint-5 steps): five medicine facts under the medicines scope, resting on the photo
✓ Pa added amlodipine the checkpoint-6 way (POST /profiles/{id}/medicines with his OK): one line (amlodipine 5 mg), a supply of 5 at one a day — five days left, inside the reorder threshold
✓ GET /profiles/{id}/feed: the supply order — now, reorder, reading, gate, story — every card rendered from State snapshot 9 (5fe4a891…), none set to autoplay, and each says why it is there:
    [now     ] now       Your tablets today  (generated)
               why: You have medicines on your list.  (fact_ids [1ac2b695…, 1db3d221…, 58595a13…, 7b457ac6…, 896072c4…, 8b77c208…])
    [today   ] reorder   Your blood pressure tablet is running low  (generated)
               why: You have about 5 days of your blood pressure tablet left.  (fact_ids [8b77c208…], gap 5 tablet…)
    [today   ] reading   Your blood pressure today  (generated)
               why: You took your blood pressure today.  (fact_ids [8f42fd86…], event_id be54233a…)
    [gate    ] gate      That is all that is new  (generated)
               why: You have seen everything new for today.  (no refs)
    [story   ] story     From your blood pressure book  (generated)
               why: This is from your own blood pressure book.  (fact_ids [05118949…])
✓ the reorder card repeats E04's own lines — "Your blood pressure tablet runs out on Saturday 19 September." — cites the medication fact 8b77c208… and says why: "You have about 5 days of your blood pressure tablet left."
✓ the reading card says his number back — "Your blood pressure today was 138 over 84." — cites fact 8f42fd86… and event be54233a…, and has a spoken twin of 3 lines
✓ paged twice with the cursor (GET …/feed?cursor=): 5 then 5 cards, all story or learning — the list is endless past the gate — and the same cursor answers the same page
✓ caps: three numbers today made three cards, one is shown — one of each kind a day, two new cards a day — and the page says what was held: {'reading': 2}
✓ quiet hours (21:00–07:00 on his wall clock, pretended with ?at=22:30 on this dev run): nothing is delivered; held: {'now': 1, 'reorder': 1, 'reading': 3, 'gate': 1, 'story': 5, 'learning': 2}
✓ a red flag jumps the queue: POST /profiles/{id}/feelings {word: fall} raised a flag before any ranking; the flag card is first, in quiet hours too, and took no place from the two a day:
    You told Nura about a fall.
    This one we do not wait for.
    Call 995 now.
✓ 'Not for me' (POST …/feed/{item}/engagement {event: dismissed}): the reading cards are held for the rest of today ({'reading': 3}); his word is a fact — declined.reading, confirmed by him, resting on the engagement event 8b813447… — and State folded it into the preference dimension (snapshot 12)
✓ Mei (+6592224500) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Mei (caregiver key: medicines, visits, readings, records, emergency) sees the caregiver supply — flag, now, notice, reorder, reading — the flag first, no gate, each with its status; the safety notice about a warfarin batch that is not the one on his box is held for her and was never on his feed:
    [flag    ] flag      This one we do not wait for  (sent)
               why: This is one of the things we never wait for.  (event_id 636dae6b…, flag_id d44bd812…)
    [now     ] now       Your tablets today  (sent)
               why: You have medicines on your list.  (fact_ids [1ac2b695…, 1db3d221…, 58595a13…, 7b457ac6…, 896072c4…, 8b77c208…])
    [today   ] notice    A notice about one batch of your blood thinner  (held)
               why: This is about your blood thinner, which is on your papers.  (fact_ids [1ac2b695…, 896072c4…], source_id 62821400…, gap warfarin, suppressed batch_do…)
    [today   ] reorder   Your blood pressure tablet is running low  (sent)
               why: You have about 5 days of your blood pressure tablet left.  (fact_ids [8b77c208…], gap 5 tablet…)
    [today   ] reading   Your blood pressure today  (dismissed)
               why: You took your blood pressure today.  (fact_ids [8f42fd86…], event_id be54233a…)
✓ the allowlist is the owner's and his chief's: Mei's caregiver key is refused, NotTheirsToManage (403)
✓ self-search: the medicine started an explainer job and a daily safety job (GET …/search-jobs, 5 jobs, all done against the fixture searcher); the explainer made a learning card "Your blood thinner and your food" citing https://www.hsa.gov.sg/consumer-safety/articles/warfarin-and-food — a source on the allowlist (GET …/sources, 6 sources) — and rerouted the page that would change a dose as a question for the memo (1), never a card:
    Your blood thinner is called warfarin.
    Green leafy food changes how well it works.
    Keep the same amount of greens each week.
    Tell your doctor before any new tablet or herb.
    This comes from Health Sciences Authority.
    This is not a doctor's advice.
    Ask your doctor.
✓ GET …/feed/cached: the last first page rendered for Pa, 5 cards, as it was — what the app keeps for an offline launch
✓ Pa reads his audit trail (500 lines): every card, page, job and engagement is on it as a write, Mei's refusal is on it by name, and the flag's escalation is 0 share line(s) — none, here, because the fall came before Mei held a key with the emergency scope
checkpoint 8 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 8 passed`. The criteria:
every card names the State snapshot it was rendered from (the column is not nullable and the table
refuses a row without it); the patient's supply comes in order — a red flag, then now, then today's
cards, then the gate, then his story, then learning — and past the gate the list pages endlessly
through story and learning without a card from outside the allowlist or outside his profile; the same
cursor answers the same page; one card of each kind a day and two new cards a day, with what was held
counted and shown to the caregiver as held, never dropped in silence; nothing is delivered between
21:00 and 07:00 on his wall clock except a red flag, which is raised before any ranking, comes first,
and takes no place from the caps; "Not for me" is his word, written as a fact (`declined.<type>`,
confirmed by him, holding until midnight) that State folds into the preference dimension and ranking
reads back; a caregiver key reads the caregiver supply narrowed to the parts of the record it covers,
with the flag first and no gate, and never a card built from his private notes; a safety notice that
does not match the batch on his pack is held for the caregiver and never sent to him; a medicine
running low is a reorder card that repeats E04's own lines and cites the medication fact; a learning card
comes only from an allowlisted, approved source in the profile's region and cites the page; the
allowlist and the search jobs are the owner's and his chief's; every line on a patient card passed
`app/safety/plain_words.py` before the card was written, and a card that fails is not made; no card
autoplays (`autoplay` is a column and it is false); the last first page is kept for an offline launch;
and every read, write, share and refusal is on the trail. If you see a ✗, the line says what was asked,
what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token and the profile id:

1. **The same words in his language.** `POST /profiles/mine` a second profile is not possible (one graph
   per person), so register a fresh number, open a profile with `"language": "ms"`, post a reading, and
   `GET /profiles/{profile_id}/feed`: the reading card says "Tekanan darah anda hari ini 138 atas 84." and
   the gate says "Itu sahaja yang baru".
2. **A search job by hand, scoped to the allowlist.** `GET /profiles/{profile_id}/sources` lists the
   allowlist for Singapore. `POST /profiles/{profile_id}/search-jobs` with `{"kind": "explainer", "terms":
   ["blood pressure"]}` runs a job now and answers with its results: the HealthHub page became a learning
   card. Name a `source_ids` entry that is not on the list and the answer is `400 {"refusal":
   "SourceNotAllowlisted"}` — and the refusal is on the trail (`GET /profiles/{profile_id}/audit`).

## How to run checkpoint 9

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having been run. Nothing reaches Meta: the WhatsApp provider is the fixture (`NURA_WHATSAPP_PROVIDER=fixture`, which `make dev` sets), which keeps what it "sends" in memory and serves media from `backend/tests/fixtures/whatsapp/`. The script drives the number through `POST /dev/whatsapp/inbound` — a dev-only door, gone outside a dev run, that walks exactly the path the signed webhook (`POST /whatsapp/webhook`) walks — and reads the replies back from it.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0011 adds the WhatsApp tables), serves on http://127.0.0.1:8000
make checkpoint N=9     # terminal 2: walks the whole scenario, about three seconds
```

Three fresh phone numbers every run — Pa, Mei his daughter, and Kit, a son nobody has let in — so it can be run again on the same `dev.db`. The "photo" Mei forwards is the lipid report of checkpoint 5, served by media id from the fixtures; the medicine on Pa's list is amlodipine, added through checkpoint 6's route so the morning card has a dose to say.

What you will see (the numbers, ids and dates change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591116167) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Mei (+6592224885) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa let Mei, his daughter, in to his record and cut her a chief key
✓ Mei wrote to the number before Pa agreed to WhatsApp: refused, ConsentWithheld, nothing kept — the one line she got says so, and names no health content:
    → Nura does not send WhatsApp messages for Pa yet.
    → Pa can turn that on in the app.
✓ Pa agreed to WhatsApp (POST /profiles/{id}/consents/whatsapp, his own basis); the words he read:
    Every morning, Nura sends you your Today page on WhatsApp.
    You can stop this at any time.
✓ Pa added amlodipine from a label (checkpoint 6's route); run_morning (POST /dev/whatsapp/morning/{id}, what the scheduler will call) sent Pa the morning card — one of the six approved templates, because Pa has not written in the last 24 hours, composed from the now and today cards of his feed (the tablets card said as today's doses) and the State they came from, through his WHATSAPP consent, verified against plain words:
    → Good morning, Pa, this is Nura.
    → Today is Monday 14 September.
    → Take 1 tablet of your blood pressure tablet with breakfast.
    → When you can, take your blood pressure.
    → Send me the 2 numbers.
✓ Mei forwarded the lipid report (POST /dev/whatsapp/inbound, media from the fixtures — the webhook's own path, no Meta): the bytes went to the SG store as a WhatsApp photo artefact, the extractor read it as a lab_report, and a review card with 7 fields waits for a yes in the app; nothing is a fact. The reply in her thread:
    → I kept the photo.
    → You can check it in the app.
✓ Mei posted "BP 150/90 this morning": the classifier heard a blood pressure and wrote a proposal — what was heard, who said it, good for a day — and nothing else: GET /facts?subject=blood_pressure is []. The read-back in her thread:
    → Did I get this right?
    → Pa's blood pressure was 150 over 90.
    → Answer yes or no.
✓ Kit (+6595551474), a number no profile knows, wrote to the number: one fixed reply, no health content, nothing stored, no thread, no line on any trail:
    → Hello, this is Nura.
    → Nura keeps health papers for families.
    → This number is not on a family list yet.
    → Ask your family to add you in the app.
    → Nura is not a doctor.
✓ Pa answered "yes": nothing of his is waiting, so nothing was written — only the poster confirms:
    → I have no question open for you.
✓ Mei answered "yes": a confirmation was minted for exactly the draft recomputed from the proposal and spent in the same unit of work; the reading is a Fact, 150/90 mmHg, confirmed_by_person Mei, resting on the event of the reading and on the message it was heard in (artefact 932bda1b…); State recomputed, snapshot 2, trigger new_fact naming it. The reply:
    → Thank you for telling me.
    → I wrote it down.
✓ Mei posted "he fell in the bathroom": a red flag (the word table in app/safety/red_flags.py) — the moment it was said (a SYMPTOM event) and the Flag on it were written first, before the message was even kept, then the message, then the escalation record naming the ladder from the keys table (owner, chief keys, others; the poster left out); nothing was extracted, no proposal. The reply in her thread, at once:
    → This one we do not wait for.
    → Call your doctor today.
    → Pa knows now.
    2026-09-14T15:06:11  Mei  write emergency red_flag  whatsapp
    2026-09-14T15:06:11  Mei  write emergency safety_escalation  whatsapp
✓ Pa answered "tired": his own word about himself, one of the three the check-in offers, so no read-back — a SYMPTOM event and a feeling fact confirmed by him, the yes minted and spent in the same request the way the app's save button does. The reply:
    → Thank you for telling me.
    → I wrote it down.
✓ Pa reads the thread (GET /profiles/{id}/whatsapp/thread, 13 messages, owner and chief only): every kept message by reference — who, when, what kind, which artefact, template or State — never the words; Kit is not on it
✓ Kit (+6595551474) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Kit, now registered but on no family list, is refused the thread: NoKey (403)
✓ Pa reads his trail (240 lines, 83 on the WhatsApp channel): every kept message is a write, every send a SHARE naming who it went to (9 of them, the refusal notice included), and the refusals are on it by name; Kit is on none of it:
    2026-09-14T15:06:11   Pa  write profile whatsapp_proposal  refused NoOpenProposal
    2026-09-14T15:06:11  Mei  read profile consent  refused ConsentWithheld
checkpoint 9 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 9 passed`. The criteria: the sender's number is their identity — it resolves to their account and to the one profile their key opens, and everything the message does happens inside that key through the same doors as the app; no thread is kept and nothing is sent about a profile until its owner has agreed to WhatsApp, in words he read; a forwarded photo is filed the way an uploaded one is (a WhatsApp artefact in the region's store, a review card waiting for a yes) and answered in the thread from the catalogue; a health event heard in free text is a proposal, not a fact, until the poster — and only the poster, from the same number, within a day — says yes, at which point a confirmation is minted for exactly that draft and spent, the fact rests on the event and on the message it was heard in, and State recomputes; a number no profile knows gets one fixed line with no health content and leaves nothing behind, not even a line on a trail; a red flag writes the Flag before anything else, answers in the thread at once, and writes the ladder from the keys table; everything proactive is one of six approved templates, sent as a template outside the 24-hour window and as text inside it, composed from State, through the plain-words verifier; the patient's own feeling word is written down on his word alone; the thread is read by the owner and his chief, by reference, never the words; and every message in or out is a line on the trail. If you see a ✗, the line says what was asked, what came back and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token (press *Authorize* and paste it) and the profile id and Mei's number from it:

1. **A no.** `POST /dev/whatsapp/inbound` with `{"from_e164": "<Mei's number>", "text": "sugar 7.2 before breakfast"}`: the answer's `outcome` is `proposal` and the reply reads it back. Then the same with `"text": "no"`: `outcome: declined`, the reply is "OK, I did not write it down.", and `GET /profiles/{profile_id}/facts?subject=blood_sugar` is still `[]`. Send `"yes"` now and the answer is `nothing_open`: a proposal is answered once.
2. **The signed webhook.** The dev door walks the webhook's path; the webhook itself checks a signature first. `POST /whatsapp/webhook` with any body and no `X-Hub-Signature-256` header answers `403 {"refusal": "NotAWebhook"}` and nothing happens. `GET /whatsapp/webhook?hub.mode=subscribe&hub.verify_token=nura-dev-webhook-secret&hub.challenge=hello` answers `hello`: the handshake a provider makes once, with the secret `make dev` sets. A wrong token is `403`.

The provider is a port (`backend/app/channels/whatsapp/provider.py`): `send_text`, `send_template`, `fetch_media`, `verify_webhook`, `parse_inbound`. The fixture behind it is the only one built, and the process refuses to start on it outside a declared dev run, the way it refuses the logging code sender. The six templates are in `backend/app/channels/whatsapp/templates.py` as names, slot lists and the words in English, Malay and Chinese; a real number carries them to Meta for approval once, and `app/channels/whatsapp/config.py` says which are approved on this number.

## How to run checkpoint 10

Three terminals the first time, at the top of the repo. Node 20 or later is needed beside the Python 3.12 the backend uses; `make web` installs the web client's packages the first time it runs (`npm ci`, about ten seconds).

```sh
make setup              # once: the backend
make dev                # terminal 1: the API on http://127.0.0.1:8000, log to backend/.dev.log
make web                # terminal 2: the app on http://127.0.0.1:5173/app/, proxying /api to the backend
make checkpoint N=6     # terminal 3, optional: gives a fresh number three medicines so Today has a Now card
```

**On the Mac.** Open http://127.0.0.1:5173 (it goes to `/app/`). Type a phone number — any Singapore-shaped one, `+65` and eight digits — and a name, tap *Send me a code*, and read the six digits from the `make dev` terminal (or `backend/.dev.log`), the way checkpoint 2's script does; nothing is sent anywhere. Type them in and tap *Sign in*. A fresh number sees the doors: tap *This is for me*, read the words (the same wording `POST /profiles/mine` records, fetched from `GET /consent/wording`), tap *I agree*. You are on Today.

**A Now card.** A fresh profile has no medicines, and Today says so in one sentence. To see the Now card, add a medicine the way checkpoint 6 does — at http://127.0.0.1:8000/docs with your token (press *Authorize*): `POST /profiles/{id}/photos` with any base64 bytes as a `image/png`, then `POST /profiles/{id}/confirmations` with `{"subject": "medicine", "label": {"generic": "amlodipine", "strength": "5 mg", "dose_text": "1 tab OM", "quantity": 30, "prescriber": "Dr Tan", "source_kind": "retail"}, "source_artifact_id": …}`, then `POST /profiles/{id}/medicines` with the same label, artefact and the `confirmation_id`. Pull the Today tab again (tap *Today*): the Now card says *Your blood pressure tablet — Take 1 tablet of your blood pressure tablet with breakfast.* with one paper button, *Taken*. Or run `make checkpoint N=6` and sign in to the app with the number it printed for Pa.

**On your iPhone, on the same Wi-Fi.** `make web` starts Vite with `--host`, so it also answers on the Mac's address: find it under *System Settings → Wi-Fi → Details*, or run `ipconfig getifaddr en0`, and open `http://<that address>:5173/app/` in Safari. Everything works the same; the code is still in the `make dev` terminal. Over plain http on a LAN address Safari will not offer *Add to Home Screen* as an app and will not install the offline worker — that needs https, which the cloud deployment brings (checkpoint 19's note will say so). On the Mac, `127.0.0.1` counts as secure, so the offline part is checked there.

**Offline, on the Mac.** Build the app and let the backend serve it: `make build-web`, then (with `make dev` running) open http://127.0.0.1:8000/app/, sign in and reach Today once. Turn Wi-Fi off, or in Safari's *Develop → Network Conditions* pick *Offline*, and reload: Today opens on the same medicines with a line saying you are not connected, and no spinner. `make web-e2e` does exactly this in Playwright.

What you will see (the operator's walk, `make web-e2e` with `make dev` serving the build):

```
✓ offline.spec.ts › Today opens offline with today's medicines
✓ today.spec.ts   › sign in, agree, Today, Taken, Hear, sign out
✓ today.spec.ts   › a refusal is one plain sentence, never the class name
✓ today.spec.ts   › the language picker changes every string and persists on the device
4 passed
```

**What "passed" means.** You signed in with a code that never travelled over the API; you opened your own papers on today's words; Today shows one Now card — one drug in your words, one whole sentence, one paper button — and *Taken* moves it to the next dose (or to *You have taken every tablet for today*) and puts the proud number up by one; every card has a *Hear* button and nothing speaks until you tap it; the tablets card and the State card are in your words with the boundary line under them; a wrong code is refused in one plain sentence; the language picker changes every word and is remembered; and on the Mac, the built app reopens offline on today's medicines with no spinner. Nothing scrolls sideways, there are no badges or counts, and the text is 20px with 56px buttons in the patient density. If a step does not do that, tell the operator which one and what you saw instead.

## Rules the operator follows between checkpoints

- Stories merge when CI is green, the safety and plain-words reviewers pass, and the operator has read the diff. `risk:high` stories get a written note in the PR saying what was checked.
- A checkpoint is not declared ready until `make checkpoint` passes end to end on a clean database.
- Anything that needs a real credential (SMS provider, licensed drug data, WhatsApp BSP, Apple) is a fixture until you say otherwise; the checkpoint says so where it applies.

## How to run checkpoint 13

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having run. Four fresh phone numbers every run — Mei, Pa, Siti the helper, Kit the son — so it can be run again on the same `dev.db`.

```sh
make dev                # terminal 1: migrates dev.db (0013 adds the family tables), serves on http://127.0.0.1:8000
make checkpoint N=13    # terminal 2: walks the whole scenario, about three seconds
```

What you will see (the numbers, ids and days change each run; the trail is in Pa's language, Malay):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Mei (+6594447692) registered by phone code and signed in (the code read from the server log)
✓ Mei set up a profile for Pa (+6593332250) on the basis of a lasting power of attorney, citing its PDF by digest e2d853e9…; she is its steward
✓ Pa (+6593332250) registered by phone code and signed in (the code read from the server log)
✓ Pa claimed the profile: he is its owner, Mei his chief on his own consent
✓ Siti (+6596662970) registered by phone code and signed in (the code read from the server log)
✓ Kit (+6595550162) registered by phone code and signed in (the code read from the server log)
✓ Pa agreed, in Malay, to let Siti (his helper) and Kit (his son) see named parts
✓ Mei cut Siti a helper key and Kit a caregiver key; the helper list, in Pa's words:
    Siti ialah pembantu anda.
    Siti boleh melihat ubat anda dan tekan Sudah ambil untuk anda.
    Siti boleh melihat kad kecemasan anda.
    Siti dapat senarai daripada Nura setiap pagi.
    Siti boleh melihatnya sehingga anda minta ia dihentikan.
✓ Mei narrowed Siti's key in place to the medicines only, on her own yes (PUT /keys/{key})
✓ widening Siti's key to the readings was refused: WouldWiden (403) — wider is a fresh consent from Pa and a new key
✓ Siti's narrowed key opens the medicines and nothing else: the roster refuses her (403)
✓ Pa let Mei in to his private notes as well (a fresh consent naming them, a chief key cut again); Mei reads the note
✓ Pa marked his private notes only me (his own yes); Mei, who read them a moment ago as his chief, is refused at once: OutOfScope notes (403), the note never left
✓ and it is on Pa's trail in his words: Mei asked to see your private notes on Monday 14 September. Only you can.
✓ the roster: Mei Monday to Friday, Kit at the weekend, 7 in the morning to 10 at night on Pa's wall clock; on Saturday 19 September at noon Kit is on duty
✓ a task "buy the water pill" for Siti: Mei tapping it done is refused, NotTheDoer (403); Siti sees it with her medicines-only key and taps it done herself
✓ the family thread: Mei's message, then the reading card (a reference to the State it was rendered from, never words); Kit reads it newest first
✓ the digest for Kit, every line through the plain-words verifier:
    Pa on Monday 14 September.
    Mei wrote on Monday 14 September:
    Pa slept well. I will come by at 6.
    Mei wrote down Pa's blood pressure on Monday 14 September.
    It was 138 over 84.
    Mei is on duty today.
✓ Mei composed a message to Pa from a template; the preview, exactly as he will see it, in Malay:
    Mei akan ambil anda pada pukul 9.
    Bawa buku tekanan darah anda.
✓ and scheduled it for 8 hours from now on WhatsApp, on her yes for exactly those lines, stamped with the State it was composed against; nothing is sent here (E11 delivers)
✓ Pa reads his trail as sentences in his language, 1 day(s), newest first:
    Isnin 14 September
      Mei menulis dalam mesej yang Nura hantar pada Isnin 14 September.
      Mei melihat kunci rekod anda pada Isnin 14 September.
      Mei melihat lawatan anda ke doktor pada Isnin 14 September.
      Mei melihat surat-surat anda pada Isnin 14 September.
      Mei melihat keadaan anda pada Isnin 14 September.
      Mei menulis dalam jawapan ya anda pada Isnin 14 September.
      Mei melihat jawapan ya anda pada Isnin 14 September.
      Mei melihat rekod anda pada Isnin 14 September.
✓ no sentence on it carries a class name, a table name or an id
✓ Mei uploaded the LPA PDF placeholder: found by its digest to be the paper the graph was set up on — one artefact, now with its bytes — tagged lpa, and listed under documents backing the stewardship and the agreement Mei gave for Pa on that basis
checkpoint 13 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 13 passed`. That is the whole of the criteria: a key is narrowed in place — fewer parts, a shorter window — on the chief's own yes and never widened (wider is a fresh consent from the patient and a new key); the patient can keep a part of his record to himself and every key on the profile stops opening it the same second, with the refused reach on his trail as a sentence he can read; the roster answers who is on duty on his wall clock, and a task is done only by the person it names; the family thread carries messages and health cards together and is read as a digest, every line through the plain-words verifier; a message to him is previewed exactly as he will see it and scheduled on a yes for those lines, and nothing is sent here; a paper behind a basis is kept by reference, tagged, and listed with what it backs. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with the profile id and tokens from it:

1. **Lift the mark.** As Pa, `POST /profiles/{profile_id}/confirmations` with `{"subject": "only_me", "scope": "notes", "only_me": false}`, then `POST /profiles/{profile_id}/privacy/notes/lift` with that `confirmation_id`. Then, as Mei, `GET /profiles/{profile_id}/notes` works again — her key was never changed, only what it opens — and Pa's `GET /profiles/{profile_id}/trail?language=en` shows both the mark and the lift as "You wrote in what only you can see on …".
2. **Read the trail in another language.** `GET /profiles/{profile_id}/trail?language=zh` as Pa: the same days and lines, in Chinese, with the day as `9月14日星期一`; nothing on any line is a class name or an id, whichever language.

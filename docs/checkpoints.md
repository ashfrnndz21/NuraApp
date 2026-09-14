# Checkpoints — where you can try the app yourself

Each checkpoint is a point where the pipeline stops being the only thing that can see the product. When a checkpoint is reached, the operator posts "Checkpoint N ready" with the exact steps, and `make checkpoint N=<n>` walks the backend part of it for you. Everything before CP7 runs on your Mac with no cloud account; nothing needs a real phone until CP8.

Statuses: `planned` → `ready` (you can run it) → `passed` (you ran it and it did what the criteria say).

| # | Name | You will see | Stories behind it | Status |
|---|------|--------------|-------------------|--------|
| 1 | Heartbeat | `make dev`, open http://127.0.0.1:8000/docs, call `GET /health` | scaffold | **ready** |
| 2 | Accounts, keys, consent, audit | Register by phone code (the code prints in the server log, no SMS), create a profile, issue a caregiver key scoped to `medicines, visits`, watch it read medicines and get refused on notes, then list the refusal in the audit trail | E00-01, E00-02, E00-07 | **ready** |
| 3 | Memory and State | Add a blood-pressure reading as a Fact with provenance, watch State recompute and record the trigger; a Fact without provenance is rejected; a key without the record cannot read State | E00-03, E00-04 | **ready** |
| 4 | Three doors, proxy, claim | Set up a profile *for someone* by phone number, try to create a second one for the same number (refused, in words that name nobody), then claim it as the patient and see the steward key become the chief key with consent recorded | E01-01, E01-02 | **ready** |
| 5 | Paper in, facts out | Upload the sample lipid report from `backend/tests/fixtures/paper/`, get a review card with per-field confidence (the unsure fields dotted), correct one value, confirm with one OK, and see Facts with provenance appear; upload the warfarin label and see the high-risk class on the card; a key without the record cannot see a card | E02-01, E02-07, E16-04 | **ready** |
| 6 | Medicines | Add three drugs from a label, see the reconciliation (refill vs dose change), the interaction check, the running count and reorder date, and the medication story in plain words; a high-risk drug refuses a dose without a label photo | E04-01…E04-07, E16-04 | planned |
| 7 | Plain words and the visit loop | Book a visit with Dr Tan; read the pre-visit brief in Malay (every line passes the plain-words verifier) and the questions card (three lines); paste the visit transcript and get the summary card with the dose change as a question for the doctor; confirm it and see the memos, the planned follow-up and the facts citing the transcript; paste a red-flag transcript and see the card carry the flag and "Telefon Dr Tan hari ini."; see a fragment refused | E22-01, E05-01, E05-02, E05-05, E05-06 | **ready** |
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
✓ GET /profiles/{id}/medicines now lists the label's facts (subject medicine → scope medicines)
✓ the high-risk label rule (E16-04): a warfarin dose fact whose provenance is not a PHOTO artefact is refused, NotFromALabelPhoto (400), and written to the trail. No route can express it — the only way to write a medicine dose over HTTP is a card from a photo — so the refusal is held at the service (app/safety/high_risk.py, a hook on before_fact_write) and proven in backend/tests/test_high_risk.py from a WhatsApp message, a PDF and a screenshot
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

The high-risk refusal is at the service, not over HTTP: the only way to write a medicine dose over the API is a card made from a photo, so there is no request that could offer a WhatsApp message or a PDF as the provenance of a warfarin dose. The rule (`NotFromALabelPhoto`, which the API would answer with 400) lives in `backend/app/safety/high_risk.py` as a hook the memory store runs before any fact is written, and is proven from a message, a PDF and a screenshot in `backend/tests/test_high_risk.py`.

## How to run checkpoint 7

The same two terminals as checkpoint 2; it does not depend on any earlier checkpoint having been run.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0009 adds the visit loop), serves on http://127.0.0.1:8000
make checkpoint N=7     # terminal 2: walks the whole scenario, about four seconds
```

Two fresh phone numbers every run, Pa and Mei, so it can be run again on the same `dev.db`. No recording is sent: the two transcripts in `backend/tests/fixtures/visits/` are written examples (the docs' example names, no real person), each with the structure a summariser would hear in it; the fixture summariser answers by the digest of the transcript text, and a model in the profile's region is a later adapter behind the same interface. The transcript text goes to the local object store under `backend/var/objects/SG/transcripts/` (ignored by git); no row holds a word of it. The script checks every patient line a second time itself, running `python3 -m app.safety.plain_words --text … --lang ms` as a command, the way you would by hand.

What you will see (the numbers, ids, dates and times change each run; the visit is booked three days from today):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591118242) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Pa opened his profile in Malay, added a blood pressure reading (138/84, taken twenty days ago) and a medicine line: the warfarin label through the review card (E02), five medicine facts, no purpose recorded
✓ Pa booked a visit with Dr Tan (POST /profiles/{id}/appointments) for 2026-09-17 at 10 in the morning, on a yes minted for exactly that booking (subject appointment): status planned
✓ the pre-visit brief (GET …/brief), in Malay, rendered from State snapshot 77aa60dc…: purpose, what changed, the open questions, what to bring — 8 lines, every one passed the plain-words verifier (checked here again, one by one, with `python3 -m app.safety.plain_words --text … --lang ms`):
    [purpose  ] Anda berjumpa Dr Tan pada Khamis 17 September.
    [purpose  ] Lawatan ini tentang tekanan darah.
    [changed  ] Sejak Isnin 14 September, ada 1 nombor baru dalam buku tekanan darah anda.
    [changed  ] Sejak Isnin 14 September, 5 perkara berubah tentang ubat anda.
    [questions] Tanya Dr Tan untuk apa Warfarin.
    [questions] Tanya Dr Tan berapa kerap perlu ambil tekanan darah.
    [bring    ] Bawa buku tekanan darah anda.
    [bring    ] Bawa ubat anda dalam kotaknya.
✓ the questions (GET …/questions): 3 for the caregiver, each naming its source — Pa's own (with his yes, subject question), a medicine line with no purpose, a reading with nothing recent (the gaps, with the facts each rests on); one card for Pa, one screen — the first three by priority and one reassurance — every line verifier-clean:
    Adakah pil air ini buruk untuk buah pinggang saya?
    Tanya Dr Tan untuk apa Warfarin.
    Tanya Dr Tan berapa kerap perlu ambil tekanan darah.
    Anda tidak perlu ingat semua ini.
      from person typed: 1 id(s) — Adakah pil air ini buruk untuk buah pinggang saya?
      from gap medicine_no_purpose: 5 id(s) — Tanya Dr Tan untuk apa Warfarin.
      from gap reading_stale: 1 id(s) — Tanya Dr Tan berapa kerap perlu ambil tekanan darah.
✓ a fragment offered as a question ("hanya bahagian untuk anda": no capital, no full stop, docs/plain-words.md rule 1) is refused by the verifier: NotPlainEnough (400), nothing written, the refusal on the trail. The English fragment ("Only the part for you.") and a memo from a deliberately bad template are refused the same way in backend/tests/test_visits.py (test_a_fragment_typed_by_a_person_is_refused_by_the_verifier, test_a_memo_from_a_template_that_is_not_plain_is_refused)
✓ Pa uploaded the routine transcript (POST …/transcript): stored as artefact 323a622a… in the SG object store, read by the fixture summariser, and answered with the summary card — 9 items, each with its span in the transcript and its confidence; the dose change is a question for the doctor, never an amount ("Tanya Dr Tan tentang jumlah baru pil air." — in English, "Ask Dr Tan about the new amount of the water pill."); nothing is a memo, a booking or a fact yet:
    Dr Tan berkata begini pada Khamis 17 September.
    Tanya Dr Tan tentang jumlah baru pil air.
    Setiap pagi, timbang berat sebelum sarapan.
    Makan malam lebih ringan.
    Anda ada ujian darah pada Isnin 28 September.
    Jangan makan selepas 12 tengah malam pada Ahad 27 September.
    Air kosong boleh.
    Bawa buku tekanan darah anda lain kali.
    Jumpa Dr Tan lagi pada Khamis 15 Oktober.
    Dr Tan mencatat tekanan darah anda.
✓ one OK saved the card: 7 memos filed against the next visit; the follow-up appears as a planned visit with Dr Tan on 2026-10-15 (GET …/appointments), needing its own confirm to be confirmed; the fact heard (blood_pressure.reading) carries the transcript artefact 323a622a… as provenance, confirmed by Pa; the dose change became a flag for the medicines reconcile (ask the doctor) and no medicine fact — his medicines are as they were
✓ the memo card (GET /profiles/{id}/memos): the current memos, one line each, in his words, verified:
    Setiap pagi, timbang berat sebelum sarapan.
    Makan malam lebih ringan.
    Anda ada ujian darah pada Isnin 28 September.
    Jangan makan selepas 12 tengah malam pada Ahad 27 September.
    Air kosong boleh.
    Bawa buku tekanan darah anda lain kali.
    Tanya Dr Tan tentang jumlah baru pil air.
✓ the red-flag transcript ("chest pain", app/safety/red_flags.py): a Flag row was written before the card was composed (on the trail as a write of flag), the card carries red_flag=true and its first line is "Telefon Dr Tan hari ini." (the English template: "Call Dr Tan today.") — a person and a day, never a diagnosis:
    Telefon Dr Tan hari ini.
    Dr Tan berkata begini pada Khamis 17 September.
    Makan ubat anda seperti biasa sehingga jumpa Dr Tan.
    Dr Tan mencatat keadaan anda.
    Dr Tan mencatat tekanan darah anda.
✓ Mei (+6592220013) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa cut Mei a caregiver key to the readings and the record; the brief and the memos refuse her: OutOfScope visits (403) — briefs, questions, summaries and memos are the visits'
✓ Pa reads his audit trail (399 lines); the refusals are on it:
    2026-09-14T10:08:20  Mei  write visits memo  refused OutOfScope
    2026-09-14T10:08:20  Mei  read visits brief  refused OutOfScope
    2026-09-14T10:08:19   Pa  write visits question  refused NotPlainEnough
checkpoint 7 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 7 passed`. The criteria: a visit is written down only on a yes minted for exactly that booking; the pre-visit brief is rendered from State in the profile's language — purpose, what changed since the record began (or since the last visit), the open questions from the gaps in the record, what to bring — and every line passes the plain-words verifier, a brief that would not being refused whole (`NotPlainEnough`) rather than shown; the questions carry their source (a gap and the facts it rests on, or the person who typed one, with his yes), and his card is one screen — three lines and a reassurance; a line that is not plain is refused by name and written to the trail; the transcript is an artefact in the region's store, never a column; the summary card renders a medicine change as a question for the doctor and never as an amount; one OK saves the card — actions become memos filed against the next visit, the follow-up becomes a planned visit that still needs its own confirm, facts heard become facts with the transcript as provenance and the person as confirmer, and the medicine change becomes a flag for the medicines reconcile and no medicine fact; the memo card is the current memos, one line each, verified again on the way out; a red-flag word writes a flag before the card is composed and puts the same-day line first, a person and a day and never a diagnosis; and a key without the visits is refused and written down. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token (press *Authorize* and paste it), the profile id and the appointment id from it:

1. **Edit a question with a yes that binds to the words.** `POST /profiles/{profile_id}/confirmations` with `{"subject": "question", "appointment_id": …, "text": "Adakah pil air ini menyebabkan saya pening?"}`, then `POST /profiles/{profile_id}/appointments/{appointment_id}/questions` with `{"text": "Adakah pil air ini menyebabkan saya letih?", "confirmation_id": …}` — different words. The answer is `400 {"refusal": "NotWhatWasConfirmed"}`. Send the words you confirmed and it is `201`, `source: person`; `GET …/questions` lists it, and `card` still has at most three questions and the reassurance.
2. **A summary is confirmed once, and rejecting writes nothing.** Upload the routine transcript again (`POST …/transcript`; the same text makes a new card). Mint the yes with `{"subject": "visit_summary", "summary_id": …, "decisions": [{"item_id": …, "decision": "rejected"}, …]}` naming every item, and confirm with those decisions: `memos`, `appointments`, `facts` and `flag_ids` are all empty, and `GET /profiles/{profile_id}/memos` is as it was. Confirm the same card again: `409 {"refusal": "AlreadyConfirmed"}`.

The brief that fails the verifier is refused at the service, not over HTTP: every template in `backend/app/reasoning/visits/strings.py` passes `make plain-words`, so there is no request that could ask for a bad line except by typing one (the fragment above). A brief and a memo rendered from a deliberately bad template are refused (`NotPlainEnough`, which the API answers with 400) in `backend/tests/test_visits.py`.

## Rules the operator follows between checkpoints

- Stories merge when CI is green, the safety and plain-words reviewers pass, and the operator has read the diff. `risk:high` stories get a written note in the PR saying what was checked.
- A checkpoint is not declared ready until `make checkpoint` passes end to end on a clean database.
- Anything that needs a real credential (SMS provider, licensed drug data, WhatsApp BSP, Apple) is a fixture until you say otherwise; the checkpoint says so where it applies.

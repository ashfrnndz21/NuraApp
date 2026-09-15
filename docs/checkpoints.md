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
| 7 | Plain words and the visit loop | Add three medicines through E04 and book a visit with Dr Tan; read the pre-visit brief in Malay (every line passes the plain-words verifier, ending on the boundary line) and see it as the visit card on the feed; the questions card (three lines and the boundary); paste the visit transcript and get the summary card with the dose change as a question for the doctor; confirm it and see the memos (and the memo card on the feed), the planned follow-up and the facts citing the transcript; paste a red-flag transcript and see the card carry the flag and "Telefon Dr Tan hari ini."; see a fragment refused | E22-01, E04, E05-01, E05-02, E05-05, E05-06 | **ready** |
| 8 | Feed (backend) | Call the feed endpoint and see the supply order (now, today, gate, story, learning) with why-am-I-seeing-this on every card; page twice with the cursor; a burst of readings is capped; quiet hours hold everything but a red flag, which jumps the queue; "Not for me" holds that kind of card for the day; Mei sees the caregiver supply; a learning card from an allowlisted source appears after the self-search job runs; a medicine running low makes a reorder card from E04's count | E21 backend (Session 8) | **ready** |
| 9 | WhatsApp (sandbox) | Mei forwards a photo to the number and it files itself as a review card and replies; she posts "BP 150/90" and gets a read-back that only her own "yes" turns into a Fact; a stranger's number gets one fixed line and nothing is stored; "he fell" writes a Flag first and escalates in-thread; the morning card goes to Pa as an approved template and his "tired" is written down; the thread is by reference and every line is on the trail | E19-01…E19-03, E19-05 | **ready** |
| 10 | Today on your phone (web) | Open the app URL in Safari on your iPhone, add it to the home screen, sign in with a phone code, see the Today shell with the Now card and Taken; it opens offline | W1 (ADR 0001) | **ready** |
| 11 | Onboarding on your phone (web) | About you one question at a time, the word cloud that deepens as you tap, the read-back with Yes and No, a paper photographed into a review card you correct and confirm, the questions it raises, the gaps and what each unlocks; the same in the caregiver density for someone you look after | W3 (ADR 0001), E01-02, E01-03, E01-04 | **ready** |
| 12 | Feed on your phone (web) | Page the vertical feed, hear a card on tap, hit the gate card | W2 (ADR 0001), the web half of E21-01, E21-03, E21-04 | **ready** |
| 13 | Family, roster and Dad's trail | Mei adds Siti as a helper and narrows her to the medicines; widening is refused; Pa marks his notes "only me" and Mei's next read is refused and on his trail in his words; the roster (Mei weekdays, Kit weekends) and a task only Siti can tap done; the family thread with a message and a reading card; Kit's digest; a message to Pa previewed in Malay and scheduled; the LPA uploaded and shown backing the stewardship | E12-01, E12-02, E12-03, E12-04, E12-06, E12-09 | **ready** |
| 14 | Emergency card, not feeling well, symptoms | Read Pa's emergency card as JSON and as the printable page (self-contained, paper, 20px, high contrast); a neighbour with an emergency-only key reads the same card; Pa says "tired today" and is told to rest with Mei told and a check-in in two hours; Pa says "chest pain" by voice (his own note, ADR 0003) and the flag is written first, State is ACT, Mei is told, and the card says "Mei knows now." then "Call the ambulance now on 995."; Pa logs "dizzy, quite a lot, since this morning" and Mei reads it in plain words; Kit with no key is refused | E13-01, E13-02, E14-01 | **ready** |
| 15 | Health biography and the first week | Mei sets up Pa (steward, as CP4) and runs his health biography: the word cloud in Malay; his settings (Malay, simple, large text, voice on, breakfast 07:30, Dr Tan, five conditions) taken by State and the profile at once; the lipid report and the medicine label through review cards; the read-back in Malay with one "no", kept as a dispute beside a fact that still holds; the questions the papers raised; the close's summary in Malay and a first week of 7 prompts from tomorrow at 07:30 SGT; Pa claims and sees the plan (one due at 07:30, one Later) and his settings in State; Kit, a caregiver, reads the settings and is refused changing them, on Pa's trail | E01-02, E01-03, E01-04 | **ready** |
| 16 | Timeline, providers, what changed, Ask | Pa with readings, a medicine on Dr Tan's name, a check-up that happened, a visit to come inside an open illness; the timeline's three anchors and first page; Mei, his chief, puts the lab photo with the illness on her yes; the providers directory with Mei's note "parking at B2" (a note naming a medicine is refused); Mei's what changed, read twice with a write between; Pa asks by voice and hears one cited line; Mei asks in text and reads lines with their citations; "do I have cancer" gets the honest line and the boundary | E03-01, E03-02, E03-03, E03-04, E03-05 | **ready** |
| 17 | Lab trends, the day's routine, calendar | Pa, born 1951, confirms two lipid reports through the review card and reads his cholesterol trend in Malay — each result against the range that fits him (the lab's own when the paper names it), the direction in words, the boundary last; Mei sets the day once on her yes and it renders to Pa as one line per moment and to her as a table; Mei uploads a small .ics with three events, gets two proposals (the lunch stored nowhere), dismisses one, and Pa's yes books the other as a planned visit; the trail shows it | E09-01, E10-01, E18-02 | **ready** |
| 18 | Handwriting, PDFs, notes, device screens | Photograph a handwritten clinic slip and see drug, dose and the rest with their confidence, the frequency asking to be typed ("Nura could not read this. Please type it."); confirming it as read is refused, Mei types it, Pa confirms; import a two-page hospital letter and see each field's page and the discharge recorded on the letter's date; a receipt says it is not a health paper; leave a voice note on a reading — his own words, so no recording consent is asked (ADR 0003) — hear it back, see it is not a fact; photograph the blood pressure machine and confirm 138/84, pulse 72, with no typing, and see State recompute; the accuracy harness over the labelled papers | E02-02, E02-03, E02-06, E02-08 | **ready** |
| 19 | Nura on your phone over https (demo) | Open the Singapore demo's https address in Safari, add it to the home screen, sign in with a test number (`+65 0…`) and the demo code, and see "Demo — not for real health information" at the top of every screen; walk checkpoints 2–6, 14, 16–18 and 21 against the same address. How-to: `docs/deploy.md` | ADR 0001, ADR 0008 | planned — needs a hosting account (Render recommended; Singapore) |
| 20 | Delivery: triggers, the ladder, the morning ritual | On a dev run's frozen clock (`NURA_FROZEN_CLOCK`, stepped with `POST /dev/clock`): Pa with his blood pressure tablet and a roster (Siti the helper, Mei on duty weekdays); at his breakfast (07:30, the one time his settings, his routine and his first week all read), the morning card goes to him as the approved WhatsApp template, once; the breakfast tablet's window closes with no Taken and the ladder asks Pa, then Siti, then Mei — the third ask goes to the roster — and stops when Siti replies "sudah beri" on WhatsApp, which writes the Taken tap; the reorder date reached goes to Mei, held for the quiet hours before 7 and capped the second time that day; at 22:30 Pa writes that he fell and the flag goes straight to the roster, neither quiet nor capped; today's top three with why; one card played as voice | E00-05, E11-01, E11-02, E11-03, E11-04, E11-05, E11-06, E11-10 | **ready** |
| 21 | Feeling cloud and smart nudges | Pa, in Malay, adds the blood pressure tablet from a label and types in a blood pressure: the cloud puts "Pening" (dizzy) first, because the new medicine's licensed monograph lists it, with a reason code on every word; Pa taps it and answers "since yesterday", and the note says what to tell Dr Tan and ends on the boundary; the strip goes after the tap; Pa taps "chest pain" — the not-feeling-well button runs for him: the flag, the family told, the urgent card, posture act, no note; no nudge today, tomorrow's is the visit (one a day, in the daytime, the proud number held); Mei reads the metrics, counts only; the Me page says the number that only goes up | E17-01…E17-05, E11-07 | **ready** |
| 22 | Visit day: logistics, recording, clips | For Pa's visit to Dr Tan tomorrow, the logistics card from the record: the time his way, Dr Tan's address, Mei's note about the place under "Mei's note" as she wrote it, who drives him — Mei, the roster says, as a suggestion that waits for a yes, then "Mei will drive you to Dr Tan" — and what to bring (his blood pressure book, his tablets in their boxes, his hospital letter); the card on his feed the day before and on the day; no recording without his agreement to Nura listening, and a viewer refused before the room is told anything; the notice said to Dr Tan by name, one recording sent on Stop, kept as a consult, heard, split by speaker with Dr Tan's yes as the first seconds; the post-visit card with each line's place in the recording; "what did Dr Tan say about the water pill" answered first with "the card is waiting for your yes", then, once it is confirmed, with the clip; the recording heard by him and the family he let in (his chief, his caregiver) and refused to a viewer, a clinic and a helper; on the phone, the Visit screen: one big *Start recording*, the notice first, a red dot and a timer, *Stop*, "Hear what Dr Tan said"; a no that keeps nothing; a hidden page that stops at once | E05-03, E05-04, E02-05, E03-05 | **ready** |
| 23 | Same words every time; the pharmacist's queue | `make language` holds every patient string in every catalogue — cards, WhatsApp, the web client — to one Malay and one Chinese line per English line and to the glossary's words (docs/plain-words.md §6), 0 failures; Pa in English (Mei holds a key), Kit in Chinese and Aminah in Malay each write down a blood pressure and every card comes back with its voice script: the numbers as words in the card's language, a pause after each line, a longer one before the boundary; the pharmacist, by staff token, reads the first cards of each type with nobody in them (`{name}`, no profile id), sees each type flagged until its first fifty are decided, rewrites a line as a proposed catalogue change that changes nothing Pa sees, and approves a new source only after a search naming it was refused; Pa's own key is refused on the queue | E22-02, E22-03, E22-04 | **ready** |
| 25 | The Record on your phone (web) | One *Papers* entry in the nav (Today · Papers · Family · Me; the Feed opens from Today) over the backend's own routes: his medicines, each line with where it came from and how sure Nura is, and the story in his language with *Hear*; a medicine added from a label photo and checked before it is saved — the severity and both medicines named — and a high-risk one from a file refused in one sentence; the reorder card's *Ask the family to order.* (a task for whoever is on duty, else his chief, and his chief told) and *I have more at home.* (the count up, on his yes); his papers waiting for a yes, a WhatsApp forward among them; his visits under the spine's three anchors, paged; an illness and a paper put with it on the chief's yes; Dr Tan and the chief's note, a note naming a medicine refused; what changed, read twice; his cholesterol against its range, the direction in words, the boundary last; the day as lines to him and a table to her, set on her yes; a blood pressure read off the machine's screen with no typing — every screen in both densities, nothing drawn over a line | W5 (ADR 0001), E03-01, E03-02, E03-03, E03-04, E04-01, E04-03, E04-05, E04-06, E09-01, E10-01, E02-04, E02-08 | **ready** |
| 26 | Family on your phone (web) | Two people on two browsers. Pa, on his iPhone in the big and simple look, opens *Family*: who can see his papers and who looked, in his words; he keeps his private notes to himself and Mei's next read is refused and on his trail; he reads what he said yes to, stops letting Kit in after the backend says what that will do (Kit is out at once), and saves the record to print; a visit his calendar proposed is booked on his yes, one at a time. Mei, in the smaller look at 360 wide, gives Siti a helper's key by role, parts and a window, makes it smaller, is told in the backend's words that wider needs Pa, closes it; puts herself on duty on weekdays and Kit at weekends, gives Siti a task only Siti can mark done; writes to the family and Kit reads the digest; previews a message to Pa in Malay, schedules it, and sees it sent; reads the week in numbers (counts only), what Nura sent to whom and by which rule, and changes the quiet hours; adds the LPA; says *I'm on it* to a red flag that reached her; the pharmacist works the review queue on a staff page by staff token | E00-02, E00-05, E00-07, E01-01, E11-05, E11-06, E12-01, E12-02, E12-03, E12-04, E12-06, E12-09, E17-05, E18-02, E22-04 (W6, ADR 0001) | **ready** |
| 27 | The patient's day on your phone (web) | On Today, *I am not feeling well* under the greeting: "tired today" typed gives the backend's card line by line — "Mei knows now.", rest, "Mei will call you today.", "Nura will ask you again in 2 hours.", the boundary last — and "chest pain" said out loud gives the urgent card, "Mei knows now." / "Call the ambulance now on 995." / "After that, call Mei." / "Nura does not decide what is wrong.", sent ahead of every other request; the wash fades to coral (no fade with Reduce Motion); with no network the offline card the phone kept, never nothing; the feeling cloud after a change in State, a word, its one question and the note kept for the visit, a red word taking the red-flag path first, the strip gone after the tap; *Write down how you feel* with how much and since when, and Mei reading it in plain words on her phone; the day's nudge with its why, *OK* or *Not today*; today's top three, one card at a time with *Next*; on the Visit screen the whole pre-visit brief, his questions added and taken off on his yes, and the post-visit card confirmed on the web, each line with where it was said, one left out, then the memo card; on the feed, "Hear what Dr Tan said" under a memo line plays that stretch alone, and a key that may not hear it gets the refusal's sentence; the number that only goes up on Me | E05-01, E05-02, E05-05, E13-02, E14-01, E17-01, E17-02, E17-04, E11-07, E11-02, E21-03, E15-01 (W7, ADR 0001, ADR 0012) | **ready** |
| — | Your family on TestFlight | The app on your phone and your dad's, against the pilot backend in-region | build-plan §6, weeks 2–8 | later — needs an Apple developer account |

**Trust documents.** Not checkpoints, but read before CP7 and before the first family on real health information (the TestFlight row): `docs/trust/` holds the SaMD boundary review (signed off before any flag ships), the recording consent pattern (counsel's sign-off before a visit is recorded on a real profile) and the PDPA data map, breach runbook and DPO (the tabletop is owed before real health information; the CP19 demo holds none, ADR 0008). E16.

## How a checkpoint is tested

- **Backend checkpoints (1–9, 13–18, 21, 22, 23)**: `make dev` in one terminal, `make checkpoint N=<n>` in another. The script runs the scenario against the local server with a fixture provider (no SMS, no real drug database, no WhatsApp) and prints each step with ✓ or ✗; it stops at the first ✗. The FastAPI page at `/docs` lets you repeat any step by hand. `make dev` also writes its log to `backend/.dev.log` (ignored by git), which is where the script reads the login codes from; `make reset-db` gives you a clean local database (stop `make dev` first).
- **Web checkpoints (10–12, ADR 0001)**: `make dev` and `make web` in two terminals, then the app in a browser — on the Mac at http://127.0.0.1:5173, on the phone at the Mac's address on the same Wi-Fi. The operator walks it first with Playwright (`make web-e2e`) and attaches screenshots to the checkpoint note; you then walk it yourself by hand.
- **Over https (19)**: needs a hosting account in Singapore, which you create — Render is the recommended one for the demo, Fly.io the alternative; `docs/deploy.md` is the whole runbook, from the account to the phone. It is a demo (ADR 0008): the fixtures, test numbers only, a banner on every screen, wiped each night. The backend checkpoints walk against it with `NURA_BASE_URL` and `NURA_DEMO_LOGIN_CODE`, except 7, 8, 9, 13 and 15, which step through dev-only routes.
- **TestFlight (last, unnumbered)**: needs your Apple developer account; the operator prepares the build and the steps.

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

## How to run checkpoint 7

The same two terminals as checkpoint 2; it does not depend on any earlier checkpoint having been run.

```sh
make setup              # once, if you have not
make dev                # terminal 1: migrates dev.db (0012_visits adds the visit loop after 0013_family), serves on http://127.0.0.1:8000
make checkpoint N=7     # terminal 2: walks the whole scenario, about four seconds
```

Two fresh phone numbers every run, Pa and Mei, so it can be run again on the same `dev.db`. No recording is sent: the two transcripts in `backend/tests/fixtures/visits/` are written examples (the docs' example names, no real person), each with the structure a summariser would hear in it; the fixture summariser answers by the digest of the transcript text, and a model in the profile's region is a later adapter behind the same interface. Pa first agrees to Nura listening at the visit (`POST /profiles/{id}/consents/recording`, the `recording` consent in his language); without it no transcript is stored and `POST …/transcript` is refused by name. The transcript text goes to the local object store under `backend/var/objects/SG/transcripts/` (ignored by git); no row holds a word of it. The three medicines come in through E04's route (`POST /profiles/{id}/medicines`, checkpoint 6), identified in the fixture drug registry, so the questions the brief raises about them — the interaction the licensed data flagged — rest on real medication lines. The script checks every patient line a second time itself, running `python3 -m app.safety.plain_words --text … --lang ms` as a command, the way you would by hand.

What you will see (the numbers, ids, dates and times change each run; the visit is booked three days from today):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591112282) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa opened his own profile (wording 1, in the app); as its owner every part is open to him
✓ Pa agreed to Nura listening at the visit and keeping what is said (POST /profiles/{id}/consents/recording, the words in Malay): no transcript is kept on a profile without this; without it POST …/transcript is refused, ConsentWithheld (403)
✓ Pa opened his profile in Malay, added a blood pressure reading (138/84, taken twenty days ago) and three medicines through E04 (POST /profiles/{id}/medicines, each from a label photo with his yes): amlodipine, warfarin and aspirin — the licensed data flagged aspirin against the warfarin already there, and every monograph says what its medicine is for
✓ Pa booked a visit with Dr Tan (POST /profiles/{id}/appointments) for 2026-09-17 at 10 in the morning, on a yes minted for exactly that booking (subject appointment): status planned
✓ Pa wrote down how he feels (POST /profiles/{id}/symptoms, typed: "pening, agak banyak, sejak pagi"): heard as dizzy, quite a lot, since this morning — his words kept as an artefact, a symptom fact resting on them
✓ the pre-visit brief (GET …/brief), in Malay, rendered from State snapshot 530d3d4b…: purpose, what changed — his symptom on a line of its own, in the symptom log's words said to him, with how much and since when anchored to that day ("pagi itu", that morning), never a count under his papers — the open questions, what to bring — 14 lines, every one passed the plain-words verifier (checked here again, one by one, with `python3 -m app.safety.plain_words --text … --lang ms`):
    [purpose  ] Anda berjumpa Dr Tan pada Khamis 17 September pukul 10 pagi.
    [purpose  ] Lawatan ini untuk memeriksa tekanan darah anda.
    [changed  ] Sejak Isnin 14 September, ada 1 nombor baru dalam buku tekanan darah anda.
    [changed  ] Sejak Isnin 14 September, 3 perkara berubah tentang ubat anda.
    [changed  ] Anda rasa pening pada Isnin 14 September.
    [changed  ] Rasanya agak teruk.
    [changed  ] Ia bermula pagi itu.
    [questions] Tanya Dr Tan sama ada aspirin dan ubat cair darah boleh dimakan bersama.
    [questions] Tanya Dr Tan berapa kerap perlu ambil tekanan darah.
    [bring    ] Bawa buku tekanan darah anda pada Khamis 17 September.
    [bring    ] Bawa ubat anda dalam kotaknya pada Khamis 17 September.
    [boundary ] Nura menyediakan ini daripada surat-surat anda.
    [boundary ] Ini bukan nasihat doktor.
    [boundary ] Tanya Dr Tan.
✓ his feed carries the visit (GET /profiles/{id}/feed): the visit card is the brief's own words — who and when, what it is about, what to bring — ending on the brief's boundary line, and why names the brief:
    Anda berjumpa Dr Tan pada Khamis 17 September pukul 10 pagi.
    Lawatan ini untuk memeriksa tekanan darah anda.
    Bawa buku tekanan darah anda pada Khamis 17 September.
    Bawa ubat anda dalam kotaknya pada Khamis 17 September.
    Nura menyediakan ini daripada surat-surat anda.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
✓ the questions (GET …/questions): 3 for the caregiver, each naming its source — Pa's own (with his yes, subject question), the interaction the licensed data flagged between two of his lines, a reading with nothing recent (the gaps, with the facts and lines each rests on); one card for Pa, one screen — the first three by priority and one reassurance — every line verifier-clean:
    Adakah pil air ini buruk untuk buah pinggang saya?
    Tanya Dr Tan sama ada aspirin dan ubat cair darah boleh dimakan bersama.
    Tanya Dr Tan berapa kerap perlu ambil tekanan darah.
    Nura simpan soalan-soalan ini untuk anda.
    Nura menulis soalan ini untuk anda tanya Dr Tan.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
      from person typed: 1 id(s) — Adakah pil air ini buruk untuk buah pinggang saya?
      from gap interaction_flagged: 3 id(s) — Tanya Dr Tan sama ada aspirin dan ubat cair darah boleh dimakan bersama.
      from gap reading_stale: 1 id(s) — Tanya Dr Tan berapa kerap perlu ambil tekanan darah.
✓ a fragment offered as a question ("hanya bahagian untuk anda": no capital, no full stop, docs/plain-words.md rule 1) is refused by the verifier: NotPlainEnough (400), nothing written, the refusal on the trail. The English fragment ("Only the part for you.") and a memo from a deliberately bad template are refused the same way in backend/tests/test_visits.py (test_a_fragment_typed_by_a_person_is_refused_by_the_verifier, test_a_memo_from_a_template_that_is_not_plain_is_refused)
✓ Pa uploaded the routine transcript (POST …/transcript): stored as artefact f7f30a64… in the SG object store, read by the fixture summariser, and answered with the summary card — 10 items, each with its span in the transcript and its confidence; the dose change is a question for the doctor, never an amount ("Tanya Dr Tan tentang jumlah baru pil air." — in English, "Ask Dr Tan about the new amount of the water pill."); nothing is a memo, a booking or a fact yet:
    Dr Tan berkata begini pada Khamis 17 September.
    Tanya Dr Tan tentang jumlah baru pil air.
    Setiap pagi, timbang berat sebelum sarapan.
    Setiap malam, makan lebih ringan.
    Anda ada ujian darah pada Isnin 28 September.
    Jangan makan selepas 12 tengah malam pada Ahad 27 September.
    Air kosong boleh.
    Bawa buku tekanan darah anda pada Khamis 15 Oktober.
    Anda berjumpa Dr Tan lagi pada Khamis 15 Oktober pukul 10 pagi.
    Anda akan tempahkannya.
    Dr Tan mencatat tekanan darah anda.
    Nura menulis apa yang Dr Tan katakan.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
✓ one OK saved the card: 7 memos filed against the next visit; the follow-up appears as a planned visit with Dr Tan on 2026-10-15 (GET …/appointments), needing its own confirm to be confirmed; the fact heard (blood_pressure.reading) carries the transcript artefact f7f30a64… as provenance, confirmed by Pa; the dose change became a flag for E04's reconcile (the generic, the kind of change, the line it is about, no amount; ask the doctor) and no line changed — his three medicines are as they were
✓ the memo card (GET /profiles/{id}/memos): the current memos, one line each, in his words, verified:
    Setiap pagi, timbang berat sebelum sarapan.
    Setiap malam, makan lebih ringan.
    Anda ada ujian darah pada Isnin 28 September.
    Jangan makan selepas 12 tengah malam pada Ahad 27 September.
    Air kosong boleh.
    Bawa buku tekanan darah anda pada Khamis 15 Oktober.
    Tanya Dr Tan tentang jumlah baru pil air.
    Nura menulis apa yang Dr Tan katakan.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
✓ and the same memos are one card on his feed: what Dr Tan said at the visit, consolidated, in his words, ending on the summary's boundary line, until the follow-up they are filed against has passed (why: 7 memo ids, the visit):
    Pada lawatan terakhir Dr Tan berkata begini:
    Setiap pagi, timbang berat sebelum sarapan.
    Setiap malam, makan lebih ringan.
    Anda ada ujian darah pada Isnin 28 September.
    Jangan makan selepas 12 tengah malam pada Ahad 27 September.
    Air kosong boleh.
    Bawa buku tekanan darah anda pada Khamis 15 Oktober.
    Tanya Dr Tan tentang jumlah baru pil air.
    Nura menulis apa yang Dr Tan katakan.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
✓ the red-flag transcript ("chest pain", app/safety/red_flags.py): a Flag row was written before the card was composed (on the trail as a write of red_flag), the card carries red_flag=true and its first line is "Telefon Dr Tan hari ini." (the English template: "Call Dr Tan today."), the next says what happened, "Beritahu Dr Tan tentang sakit dada hari ini." — a person, a day and what was heard, never a diagnosis; the word is found in the raw transcript itself, not only in what the summariser chose to report:
    Telefon Dr Tan hari ini.
    Beritahu Dr Tan tentang sakit dada hari ini.
    Dr Tan berkata begini pada Khamis 17 September.
    Dr Tan kata ubat anda kekal sama.
    Dr Tan mencatat apa yang anda rasa.
    Dr Tan mencatat tekanan darah anda.
    Nura menulis apa yang Dr Tan katakan.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
✓ Mei (+6592228226) registered by phone code: asked (202, no code in the answer), read the six digits from backend/.dev.log — no SMS — and signed in (200, token issued)
✓ Pa cut Mei a caregiver key to the readings and the record; the brief and the memos refuse her: OutOfScope visits (403) — briefs, questions, summaries and memos are the visits'
✓ Pa reads his audit trail (500 lines); the refusals are on it:
    2026-09-14T15:39:38  Mei  write visits memo  refused OutOfScope
    2026-09-14T15:39:38  Mei  read visits brief  refused OutOfScope
    2026-09-14T15:39:35   Pa  write visits question  refused NotPlainEnough
checkpoint 7 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 7 passed`. The criteria: a visit is written down only on a yes minted for exactly that booking; the pre-visit brief is rendered from State in the profile's language — purpose, what changed since the record began (or since the last visit), every symptom written down since then on a line of its own in the symptom log's words with how much and since when and never counted under his papers (E14-01), the open questions from the gaps in the record, what to bring — on one page (at most 21 lines, a section that would run over folded into one line saying how many more), and every line passes the plain-words verifier, a brief that would not being refused whole (`NotPlainEnough`) rather than shown; the questions carry their source (a gap and the facts and lines it rests on — an interaction the licensed data flagged, a reading with nothing recent — or the person who typed one, with his yes), and his card is one screen — three lines and a reassurance, then the boundary line the questions carry; the brief, the summary card and the memo card end on their boundary lines too (E16-01), and every row carries it; inside the week before the visit the visit card on his feed is the brief's own words, ending on the brief's line, and after the visit the memo card on his feed repeats the memos in his words until the follow-up they are filed against has passed; a line that is not plain is refused by name and written to the trail; the transcript is an artefact in the region's store, never a column; the summary card renders a medicine change as a question for the doctor and never as an amount, and names a medicine only when the licensed register knows it; one OK saves the card — actions become memos filed against the next visit, the follow-up becomes a planned visit that still needs its own confirm, facts heard become facts with the transcript as provenance and the person as confirmer, and the medicine change becomes a flag for E04's reconcile — the generic, the kind of change, the line it is about, never an amount — while every medication line stays exactly as it was; the memo card is the current memos, one line each, verified again on the way out; a red-flag word — in the raw transcript, not only in what the summariser reported — writes a flag before the card is composed and puts the same-day lines first: call the doctor, and what he should hear about, a person and a day and never a diagnosis; a key that holds the visits to read — a viewer's, a clinic's — cannot write a transcript, confirm a summary or change a question (`NotTheirsToChangeVisits`, 403); and a key without the visits is refused and written down. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token (press *Authorize* and paste it), the profile id and the appointment id from it:

1. **Edit a question with a yes that binds to the words.** `POST /profiles/{profile_id}/confirmations` with `{"subject": "question", "appointment_id": …, "text": "Adakah pil air ini menyebabkan saya pening?"}`, then `POST /profiles/{profile_id}/appointments/{appointment_id}/questions` with `{"text": "Adakah pil air ini menyebabkan saya letih?", "confirmation_id": …}` — different words. The answer is `400 {"refusal": "NotWhatWasConfirmed"}`. Send the words you confirmed and it is `201`, `source: person`; `GET …/questions` lists it, and `card` still has at most three questions and the reassurance.
2. **A summary is confirmed once, and rejecting writes nothing.** Upload the routine transcript again (`POST …/transcript`; the same text makes a new card). Mint the yes with `{"subject": "visit_summary", "summary_id": …, "decisions": [{"item_id": …, "decision": "rejected"}, …]}` naming every item, and confirm with those decisions: `memos`, `appointments`, `facts` and `flag_ids` are all empty, and `GET /profiles/{profile_id}/memos` is as it was. Confirm the same card again: `409 {"refusal": "AlreadyConfirmed"}`.

The brief that fails the verifier is refused at the service, not over HTTP: every template in `backend/app/reasoning/visits/strings.py` passes `make plain-words`, so there is no request that could ask for a bad line except by typing one (the fragment above). A brief and a memo rendered from a deliberately bad template are refused (`NotPlainEnough`, which the API answers with 400) in `backend/tests/test_visits.py`.

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

## How to run checkpoint 17

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having run. Two fresh phone numbers every run — Pa and Mei, his daughter — so it can be run again on the same `dev.db`. The two lipid reports are the placeholder bytes of `backend/tests/fixtures/paper/`: the 2023 one from checkpoint 5 and a synthetic 2025 one from Bukit Lab (a fictional lab) whose header names the lab, his year of birth and his sex. The reference ranges are the fixture table `backend/tests/fixtures/labs/ranges.json`, each row named by its published source; no licensed table and no model is called. Mei's calendar is a small .ics the script writes in memory, with three events in the coming fortnight.

```sh
make dev                # terminal 1: migrates dev.db (0017 adds the trend card, routine, connector and proposal tables), serves on http://127.0.0.1:8000
make checkpoint N=17    # terminal 2: walks the whole scenario, about three seconds
```

What you will see (the numbers, ids and days change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591718072) registered by phone code and signed in (the code read from the server log)
✓ Pa opened his own profile, in Malay
✓ Pa confirmed two lipid reports through the review card, one yes each: 7 September 2023 (7 facts, triglycerides corrected to 54) and 29 August 2025 from Bukit Lab (7 facts, including the lab, his year of birth 1951 and his sex from the report's header) — every fact names its photo and Pa as confirmer
✓ Pa's cholesterol trend (GET /trends/total_cholesterol), rendered from State 66f4e9a8… as card 5a75b875… with the boundary line: each result against the range that fits him on the day — his age band read from the 1950s, never the year — the 2025 one against Bukit Lab's own printed range, the 2023 one against the guideline table (ncep-atp3-2001); the direction over the last three, by arithmetic:
    2023-09-07  230 mg/dL  above  against under 200 mg/dL (ncep-atp3-2001)  ← artefact 6107e3ac…
    2025-08-29  212 mg/dL  above  against under 200 mg/dL (lab:bukit_lab)  ← artefact 830911c3…
    In his words, in Malay:
    Kolesterol anda ialah 212 pada Jumaat 29 Ogos 2025.
    Julat pada ujian darah anda ialah bawah 200.
    Ia di atas julat pada ujian darah anda.
    Ia telah turun sejak Khamis 7 September 2023.
    Nura menyusun ujian darah anda mengikut tarikh.
    Ini bukan nasihat doktor.
    Tanya doktor anda.
✓ Mei (+6591727578) registered by phone code and signed in (the code read from the server log)
✓ Pa let Mei in to his medicines, visits and readings, and cut her a caregiver key
✓ Pa added amlodipine 5 mg from its label, once a day in the morning, on his own yes
✓ Mei set the day once (PUT /routine) on her own yes for exactly it — the same yes offered for another hour was refused, NotWhatWasConfirmed (400): his anchors, the blood pressure when he wakes, a walk after dinner, the Today page at 7
✓ Pa reads his day (GET /routine): one line per moment, in Malay, every line verified
    Nura hantar halaman Hari Ini anda pukul 7 pagi.
    Apabila anda bangun, periksa tekanan darah anda.
    Semasa sarapan, ambil 1 biji ubat tekanan darah anda.
    Semasa makan malam, pergi berjalan kaki.
✓ Mei reads the same day as a table (the caregiver's persona): times, dose codes, prompts
    wake      06:30  —                                blood_pressure
    breakfast 07:30  amlodipine 5 mg ×1 od            
    lunch     12:30  —                                
    dinner    18:30  —                                walk
    bed       22:00  —                                
✓ connecting before agreeing was refused, ConsentWithheld (403); Pa then agreed to the calendar in Malay and connected it (POST /connectors/calendar). The words he read:
    Nura membaca kalendar anda untuk mencari lawatan ke doktor.
    Nura menyimpan lawatan yang dijumpai sahaja.
    Yang lain dalam kalendar anda tidak disentuh.
    Tiada apa-apa ditambah sehingga anda kata ya.
    Nura tidak pernah menulis dalam kalendar anda.
    Anda boleh berhenti pada bila-bila masa.
✓ Mei uploaded a .ics with three events (POST /connectors/{c}/scan): 3 read, 2 proposed, 1 dropped — the lunch with Ah Kow matched no provider and no health word, and nothing of it, nor anyone's name in any event, was written anywhere. Candidates, never visits:
    Dr Tan follow-up   Thu 24 Sep 10:00  matched keyword 'doctor'  → Dr Tan (doctor)  proposed
    Dialysis SGH       Fri 18 Sep 09:00  matched keyword 'hospital'  → Singapore General Hospital (hospital)  proposed
✓ Mei dismissed 'Dialysis SGH' (not Pa's): nothing booked
    What Pa reads, in Malay:
    Nura jumpa lawatan ke Dr Tan dalam kalendar.
    Ia pada Khamis 24 September, pukul 10 pagi.
    Tekan Ya untuk tambah ke lawatan anda.
✓ Pa said yes (POST /confirmations, subject appointment_proposal) and accepted: Dr Tan added to his directory and the visit booked as PLANNED on his yes, appointment 467c23e5…; accepting again is refused, AlreadyDecided (409)
    Nura jumpa lawatan ke Dr Tan dalam kalendar.
    Ia pada Khamis 24 September, pukul 10 pagi.
    Ia sudah ada dalam lawatan anda.
✓ with a visit to Dr Tan on the spine, the trend's last line names him:
    Nura put your blood tests side by side.
    This is not a doctor's advice.
    Ask Dr Tan.
✓ Pa's trail (200 lines) shows every step and every refusal by name:
    2026-09-14T15:42:55   Pa  write records   trend_card             written
    2026-09-14T15:42:56  Mei  write medicines routine                NotWhatWasConfirmed
    2026-09-14T15:42:56  Mei  write medicines routine                written
    2026-09-14T15:42:56   Pa  read visits    consent                ConsentWithheld
    2026-09-14T15:42:56   Pa  write visits    connector              ConsentWithheld
    2026-09-14T15:42:56   Pa  write visits    connector              written
    2026-09-14T15:42:56  Mei  write visits    appointment_proposal   written
    2026-09-14T15:42:56  Mei  write visits    appointment_proposal   written
    2026-09-14T15:42:56  Mei  write visits    appointment_proposal   written
    2026-09-14T15:42:56   Pa  write visits    provider               written
    2026-09-14T15:42:56   Pa  write visits    appointment            written
    2026-09-14T15:42:56   Pa  write visits    appointment_proposal   written
    2026-09-14T15:42:56   Pa  write visits    appointment_proposal   AlreadyDecided
    2026-09-14T15:42:56   Pa  write records   trend_card             written
checkpoint 17 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 17 passed`. The criteria: a trend is his confirmed results for one analyte, each with its provenance, each placed against the range that fits him on the day — his age band from the decade he was born in (never the year), his sex when the record holds it, and the lab's own printed range when the paper names the lab, else the published guideline row — with the direction over the last three results in words, by arithmetic; it is rendered from a State checked against the record and written as a card carrying the boundary line, which is last; a word that places his number (above, below, inside) is only ever said beside the lab's own range ("the range on your blood test", his words for it), and no line names a cause or a treatment. The day is set once, on the yes of the person setting it, for exactly those times (another hour is refused, `NotWhatWasConfirmed`); his medicines sit at the anchors their dose codes name; it renders to him as one verified line per moment and to Mei as a table. The calendar is connected only on its own consent, in his language; a scan proposes only events that name a provider or carry a health word, never books one, and keeps nothing of any other event or of anyone's name; a proposal becomes a planned visit only on a person's yes for exactly it, and a second yes is refused (`AlreadyDecided`). Every step and every refusal is on his trail by name. If you see a ✗, the line says what was asked, what came back and what was expected; tell the operator and paste the line.
## How to run checkpoint 10

Three terminals the first time, at the top of the repo. Node 20 or later is needed beside the Python 3.12 the backend uses; `make web` installs the web client's packages the first time it runs (`npm ci`, about ten seconds).

```sh
make setup              # once: the backend
make dev                # terminal 1: the API on http://127.0.0.1:8000, log to backend/.dev.log
make web                # terminal 2: the app on http://127.0.0.1:5173/app/, proxying /api to the backend
make checkpoint N=6     # terminal 3, optional: gives a fresh number three medicines so Today has a Now card
```

**On the Mac.** Open http://127.0.0.1:5173 (it goes to `/app/`). Type a phone number — any Singapore-shaped one, `+65` and eight digits — and a name, tap *Send me a code*, and read the six digits from the `make dev` terminal (or `backend/.dev.log`), the way checkpoint 2's script does; nothing is sent anywhere. Type them in and tap *Sign in*. A fresh number sees the doors: tap *This is for me*, read the words (the same wording `POST /profiles/mine` records, fetched from `GET /consent/wording`), tap *I agree*. You are on Today.

**A Now card.** A fresh profile has no medicines, and Today says so in one sentence. To see the Now card, add a medicine the way checkpoint 6 does — at http://127.0.0.1:8000/docs with your token (press *Authorize*): `POST /profiles/{id}/photos` with any base64 bytes as a `image/png`, then `POST /profiles/{id}/confirmations` with `{"subject": "medicine", "label": {"generic": "amlodipine", "strength": "5 mg", "dose_text": "1 tab QDS", "quantity": 120, "prescriber": "Dr Tan", "source_kind": "retail"}, "source_artifact_id": …}`, then `POST /profiles/{id}/medicines` with the same label, artefact and the `confirmation_id`. Tap *Today*. Four doses a day hang on breakfast (05:00–11:00), lunch (11:00–15:00), dinner (16:00–21:00) and bed (20:00–24:00): while one of those windows is open the Now card says *Your blood pressure tablet — Take 1 tablet of your blood pressure tablet …* with its source line (*This comes from the label you kept on …*) and one paper button, *Taken*. Once a window has closed untapped, the card is the medicine story's own lines for a forgotten dose (*If you forgot, leave it.* … *Never take 2 at once.*) and there is no *Taken*. Between windows it says *There is nothing to take right now.* The client never works out which dose is due; `GET /profiles/{id}/medicines/today` says `due_now` and `missed` for each.

**On your iPhone, on the same Wi-Fi.** `make web` starts Vite with `--host`, so it also answers on the Mac's address: find it under *System Settings → Wi-Fi → Details*, or run `ipconfig getifaddr en0`, and open `http://<that address>:5173/app/` in Safari. Everything works the same; the code is still in the `make dev` terminal. Over plain http on a LAN address Safari will not offer *Add to Home Screen* as an app and will not install the offline worker — that needs https, which the cloud deployment brings (checkpoint 19's note will say so). On the Mac, `127.0.0.1` counts as secure, so the offline part is checked there.

**Offline, on the Mac.** Build the app and let the backend serve it: `make build-web`, then (with `make dev` running) open http://127.0.0.1:8000/app/, sign in and reach Today once. Turn Wi-Fi off, or in Safari's *Develop → Network Conditions* pick *Offline*, and reload: Today opens on the page the phone kept — *Nura cannot reach the internet right now.*, *Nura last read your papers on Monday 14 September at 8:05 pm.*, and today's list of tablets under *This comes from your Today page.* — with no Now card, no *Taken* and no spinner. The next day, still offline, the kept page is gone from the phone and Today shows only *Nura cannot reach your papers right now.* and the emergency card. Sign out, or a key closed or narrowed since, leaves nothing of the papers on the phone. `make web-e2e` does all of this in Playwright.

What you will see (the operator's walk, `make web-e2e` with `make dev` serving the build):

```
✓ midnight.spec.ts › crossing midnight in Singapore: Today reads the new day and still says no medicines
✓ offline.spec.ts › offline: the kept page as a dated list with no Taken; past midnight only the emergency card
✓ today.spec.ts   › sign in, agree, Today, Taken only when due, Hear, sign out clean
✓ today.spec.ts   › a refused read clears the phone's copy and is said in one plain sentence
✓ today.spec.ts   › a key without the records scope opens Today on the medicines and the feed, with no State card
✓ today.spec.ts   › a server error on reopening keeps him on Today, never back at sign-in
✓ today.spec.ts   › a wrong code is one plain sentence, never the class name
✓ today.spec.ts   › the language picker changes every string and persists on the device
8 passed
```

**What "passed" means.** You signed in with a code that never travelled over the API; you opened your own papers on today's words; Today shows a Now card only for the dose the backend marks due — one drug in your words, one whole sentence, its source line, one paper button — and *Taken* puts the proud number up by one (the days you took your tablets, whoever tapped *Taken*, counted by the backend); a dose whose moment has passed shows the medicine story's own lines and no *Taken*; *For you today* is the feed's cards for today, or, when it has none, the State card under Nura's own boundary lines and the medicines card with the questions for the doctor; every card has a *Hear* button and nothing speaks until you tap it; a refused read is one plain sentence and leaves nothing behind; a wrong code is refused in one plain sentence; the language picker changes every word and is remembered; and on the Mac, the built app reopens offline on today's list, dated, and past midnight on the emergency card alone. Nothing scrolls sideways, there are no badges or counts, and the text is 20px with 56px buttons in the patient density. If a step does not do that, tell the operator which one and what you saw instead.

## How to run checkpoint 18

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having run. Two fresh phone numbers every run, Pa and Mei, so it can be run again on the same `dev.db`.

```sh
make dev                # terminal 1: migrates dev.db (0018 adds the note on an event and two columns on the card), serves on http://127.0.0.1:8000
make checkpoint N=18    # terminal 2: walks the whole scenario, about three seconds
```

No photo, PDF or recording is sent. The papers are the redacted samples in `backend/tests/fixtures/paper/` — a small placeholder byte string each (a PNG signature, or a `%PDF-1.4` header, and a label) and a JSON file that says what the extractor reads off it; the voice note is a placeholder too, and `backend/tests/fixtures/voice/` says what the fixture transcriber hears. The bytes go to the local object store under `backend/var/objects/SG/`. The real handwriting, PDF and screen recognisers, and a speech provider in the region, are later adapters behind the same two ports. The last step runs the accuracy harness (`python3 -m tests.paper_accuracy`) from the backend directory, the way you would.

What you will see (the numbers, ids and times change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591816634) registered by phone code and signed in (the code read from the server log)
✓ Mei (+6592828419) registered by phone code and signed in (the code read from the server log)
✓ Pa opened his profile and cut Mei a caregiver key to his record and his readings
✓ Pa photographed Dr Tan's handwritten clinic slip (offered as a clinic_slip): drug, dose and the rest read with their confidence; the frequency, scrawled, came back unreadable — no value, never guessed — with the lines the card shows:
    visit.doctor                   Dr Tan                   confidence 0.88  clear
    medicine.name                  Amlodipine               confidence 0.86  clear
    medicine.strength              5 mg                     confidence 0.84  clear
    medicine.dose                  1 tablet                 confidence 0.81  clear
    medicine.frequency             —                        confidence 0.12  unreadable — Nura could not read this. Please type it.
    visit.next_visit               2026-12-10               confidence 0.66  dotted
✓ confirming the frequency as read is refused: UnreadableField (400) — it is typed in, or rejected
✓ Mei, with her key to the record, typed what the slip says — "once a day in the morning"; the field names her, the card is still open
✓ Pa confirmed the card: 6 facts, each resting on the photo and on the visit the slip records (an event on 10 September); the frequency is Mei's words, confirmed by Pa
✓ Pa imported his two-page hospital letter from the portal (POST /profiles/{id}/imports): a PDF artefact, read as a discharge_letter dated 2026-08-20, every field with its page:
    page 1  discharge.admitted_on          2026-08-16               confidence 0.95  clear
    page 1  discharge.discharged_on        2026-08-20               confidence 0.96  clear
    page 1  discharge.reason               heart failure            confidence 0.89  clear
    page 2  discharge.weight_at_discharge  68.5 kg                  confidence 0.91  clear
    page 2  visit.next_visit               2026-09-29               confidence 0.84  clear
    page 2  visit.doctor                   Dr Tan                   confidence 0.74  dotted
✓ one yes: the discharge recorded as an event on 20 August, and 6 facts naming it and the PDF, valid from the date on the letter
✓ the shop receipt forwarded by email is an open card with no fields and one line: "This does not look like a health paper."
✓ a photo offered as a PDF is refused before a byte lands: NotAPdf (400)
✓ Pa typed this morning's blood pressure (142/88) and left a voice note on it: his own words, kept as a voice artefact on the record consent — no recording consent asked or on file (ADR 0003) — and heard at 0.91 as "I took it after my walk. I felt fine, only a little tired."
✓ recall finds the note, cited with its event: "You left a note on Monday 14 September."
✓ Mei opens the note on the reading and plays it back (audio/m4a, 41 bytes, the same Pa sent): hearable, and not a fact — his facts are the same 13 as before
✓ Pa photographed his blood pressure machine's screen (POST /profiles/{id}/readings/photo): read with no typing — the numbers, their units, the machine and the time on its screen:
    device.kind                    blood_pressure_monitor   confidence 0.90  clear
    blood_pressure.systolic        138 mmHg                 confidence 0.97  clear
    blood_pressure.diastolic       84 mmHg                  confidence 0.95  clear
    heart_rate.pulse               72 /min                  confidence 0.93  clear
    reading.taken_at               2026-09-14T07:42         confidence 0.86  clear
✓ one yes: a reading event at 7.42 on his clock and its facts — blood_pressure.reading {systolic 138, diastolic 84} mmHg, the shape POST /readings writes, and heart_rate.reading {pulse 72} — State recomputed, snapshot 13 → 15, trigger new_fact naming fact 5390d854…
✓ a lab report sent as a machine's screen is an open card with no fields: "This does not look like the screen of a machine."
✓ the accuracy harness over every labelled paper (python3 -m tests.paper_accuracy): harness: 8 papers (8 read as the right kind), 39 labelled fields — 37 read right (94.9%), 2 caught and put to a person, 0 silently wrong, 0 dropped, 0 invented: 100.0% read right or put in front of a person
✓ Pa reads his trail (365 lines); every refusal of this walk is on it:
    2026-09-14T15:43:32   Pa  write records artifact  refused NotAPdf
    2026-09-14T15:43:32   Pa  read records review_card  refused UnreadableField
checkpoint 18 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 18 passed`. The criteria: a handwritten slip is read with a confidence on every field, and a field Nura could not read carries no value, says "Nura could not read this. Please type it.", and is never confirmed as read — someone holding the record types it, the field names who did, and the facts only land on the patient's yes; a clinic slip and a hospital letter are written as the visit and the discharge they record, on the date on the paper, and their facts name that event and the page; a PDF is read page by page, a PDF that is not a health paper is an open card that says so, and anything that is not a PDF is refused before a byte lands; a voice note on an event is the writer's own words and rests on the consent to hold the record, not the recording consent, which is for consults (ADR 0003); it is kept as a voice artefact in the region, is heard back byte for byte, and its words are kept by reference and never become a fact; a machine's screen is read into the numbers, their units, the machine and the time with no typing, and one yes writes one reading event and its facts in the shape a typed reading takes, and State recomputes; a photo sent as a machine's screen that is not one says so; every labelled paper is either read right or put in front of a person; every refusal is on the trail. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**Three things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token and the profile id from it:

1. **A private scribble.** `POST /profiles/{profile_id}/events/{event_id}/notes` on the reading's event with `"kind": "scribble"`, the base64 of a small PNG of your own, `"content_type": "image/png"`, any `captured_at`, `"private": true` and a `"label"` of a few words. Pa's `GET …/notes` lists it; Mei's (her token) does not, and her `GET …/notes/{note_id}/content` is `404 {"refusal": "NoSuchEventNote"}`. A label over 80 characters is `400 {"refusal": "NotALabel"}`.
2. **Half a blood pressure.** Upload the machine's screen again (`POST /profiles/{profile_id}/readings/photo`, the same bytes make a new card), mint an OK rejecting only the diastolic, and confirm: `400 {"refusal": "NotAWholeReading"}`, and nothing is written — a reading is both numbers or neither.
3. **The harness by itself.** `cd backend && python3 -m tests.paper_accuracy` prints the accuracy field by field. `backend/tests/fixtures/paper/README.md` says how to add one of your own papers, redacted, with its labelled answer; the harness then measures it the same way.

## How to run checkpoint 11

Onboarding is the web client's (W3) over E01's backend (#117): the condition graph, the settings, the sitting and the first week, with E02's photos, imports and review cards, E05's visit list and E12's sharing. Nothing is mocked.

```sh
make dev                # terminal 1: the API on http://127.0.0.1:8000, log to backend/.dev.log
make web                # terminal 2: the app on http://127.0.0.1:5173/app/ (proxies /api)
printf '\x89PNG\r\n\x1a\nnura-paper-placeholder:lipid-panel-2023-09-07\n' > ~/Desktop/lipids.png
printf '\x89PNG\r\n\x1a\nnura-paper-placeholder:warfarin-label-2024-03-12\n' > ~/Desktop/label.png
printf '%%PDF-1.4\nnura-paper-placeholder:discharge-letter-2026-08-20\n' > ~/Desktop/letter.pdf
                        # redacted papers the fixture extractor knows, as the bytes it knows them by
```

**For yourself.** Open http://127.0.0.1:5173, sign in with a fresh number and the code from the `make dev` terminal, tap *This is for me*, read the words, *I agree*. Onboarding starts (there is a *Set up later* on the first screen, and *Set up Nura* under Me to come back).

1. **About you** — *A few things about you*, with the sitting's own lines, then one question per screen in big type: the name Nura uses, your language (the app switches the moment you tap it), the decade you were born in, your doctor, breakfast, seven yes/no questions (bigger writing, darker writing, reading out loud, bigger buttons, one thing at a time, saying back what it understood, a second reminder), and how much to show at once. A yes to bigger writing, bigger buttons or one thing at a time, or *A little, kept simple*, keeps the big-and-simple look.
2. **The word cloud** — *What is part of your health?* The common words are biggest and on the first screen. Tap *High blood pressure*: it turns plum, the phone says it, and what often goes with it (*Blood pressure tablets*) appears right after it. Tap *High cholesterol* too and watch *See a heart doctor* grow. *Show more words* brings the rarer ones. *That is everything* saves About you and the words in one step.
3. **Your papers** — *Now, your papers* and the sitting's lines. *Choose a file instead* and pick `lipids.png`: the review card says *This is a blood test.* and the date on the paper, each line in your words with its number; the ones Nura is unsure of have a dotted underline and *Please check this one.* Change *The blood fats* from 64 to 54 (the paper's number), *Leave this one out* on another line, *Looks right*: *Nura wrote it down.* `letter.pdf` goes the import way and comes back as a card like any photo. *That is all my papers*.
4. **Read-back** — *Here is what Nura understood*, one line per screen with *This is 1 of N.*: *You told us: High blood pressure.*, *Your doctor is …*, *Your cholesterol was 230 on …*, each with *Yes, that is right* / *No, that is not right*. A no is kept as a dispute beside the fact, and Nura says who will look at the paper again.
5. **Questions** — *A few questions about your papers*, one at a time, each whole line with where it came from (*This comes from what you told Nura on …*); *Keep this one* / *Not this one*. A kept question goes on the next visit's list when one is booked, and otherwise waits and moves there when one is.
6. **Your app is ready** — what the sitting did (*Nura saved one of your papers.*), then the one card Nura will ask for first, the day it will (*tomorrow at breakfast*), and how many follow. *Later* sends it to the back; the tablets card's photo button (pick `label.png` on the Mac) comes back with that gap closed; the breakfast card asks that one question; the card for someone to see your papers takes their name, number and the parts, shows the backend's words for exactly those, and lets them in on *I agree*. *Open Nura* goes to Today.

At http://127.0.0.1:8000/docs, `GET /profiles/{id}/facts?subject=lipid_panel` shows the facts you confirmed: the blood fats at 54, the line you left out absent, each with the photo as its provenance; `GET /profiles/{id}/biography` shows each question with its State id and source line.

**For someone else.** Sign in with another number, *This is for someone else*, set up Pa. The same steps come in the caregiver density, in his name (*A few things about Pa*, *Now, Pa's papers*): every About question on one page, the read-back and the questions as lists, and the whole first week. Choosing Malay for him changes neither your phone's language nor the language of your screens.

**On the phone.** Same as checkpoint 10 (`http://<Mac's address>:5173/app/`). *Take a photo* opens the back camera. A real photo is not one of the fixture papers, so until the real extractor exists (E02) Nura answers *Nura could not read this page.* — that is the fixture, not the screen.

What you will see (the operator's walk: `make build-web`, then `make web-e2e`, which starts `make dev` with the clock frozen):

```
✓ onboarding.spec.ts › the patient's own onboarding: about you, the cloud, a paper, the read-back, questions, the first week
✓ onboarding.spec.ts › the caregiver density, for a chief setting up her father
✓ onboarding.spec.ts › his language takes effect the moment he picks it
✓ onboarding.spec.ts › papers of every kind: a hospital letter as a PDF, a page that is not a health paper, a line Nura could not read
✓ onboarding.spec.ts › the Ready screen's other actions: breakfast from its card, and one person let in
✓ onboarding.spec.ts › a question kept with a visit booked goes on that visit's list at once (E05)
✓ today.spec.ts      › (checkpoint 10's walk, with one "Set up later" step)
```

**What "passed" means.** Every question was one thing on one screen with 56px buttons, nothing drawn over a line and nothing sideways; the word cloud showed the common words without scrolling, grew what your taps pointed at, and spoke only when you tapped; every headline, read-back line, question and gap card was the backend's whole sentence, the questions with their State and where they came from; your no was kept; the review card said how sure Nura was in words, took your correction exactly as typed, never confirmed a line it could not read, and saved facts only on your one *Looks right*; a kept question reached the visit's list in your words; the words you agreed to were exactly the words kept; a refusal was one plain sentence; and nothing from onboarding was left on the phone.

## How to run checkpoint 12

The same terminals as checkpoint 10 (`make dev`, and `make web` for the phone). It does not depend on another checkpoint having run: the first step gives a fresh number a week of blood pressures and a medicine running low, so the feed has something in every section.

```sh
make dev                # terminal 1: the API on http://127.0.0.1:8000
make web                # terminal 2: the app on http://127.0.0.1:5173/app/ (proxies /api)
make checkpoint N=8     # terminal 3, optional: checkpoint 8 fills Pa's feed and prints his number
```

**On the Mac.** Sign in as in checkpoint 10 with the number checkpoint 8 printed for Pa (or any fresh number, then add two blood pressures in the app and a medicine at http://127.0.0.1:8000/docs as checkpoint 10 describes). On Today, under *For you today*, tap *See more for you*. The feed fills the screen, one card at a time: swipe up (or press Page Down) for the next. The order is the backend's and the app never changes it: a red flag first if there is one, then *Now* (*Your tablets today* — its one button, *See your tablets*, goes back to Today, where *Taken* is), today's cards (*Your blood pressure tablet is running low*, *Your blood pressure today*), then the gate — *That is all that is new today. Do you want to keep going?* — with one button, *Keep going*. Past the gate come his story (*From your blood pressure book*, *The number that only goes up*, *From your papers*) and learning (*Taking your blood pressure at home*, which ends on *This comes from HealthHub.* and the boundary lines *Nura explains one thing in simple words. / This is not a doctor's advice. / Ask your doctor.*). Keep swiping: past the gate the list does not end — the next page loads before you reach the bottom, and his story and learning come round again. Every card says why it is there in small type under its lines.

**The four buttons on every card.** *Hear* reads the card out, and only when you tap it: nothing plays when a card arrives, and the next card never starts by itself; swipe away and the voice stops. (The backend's pre-rendered voice is E11's route; until it exists, the phone reads the card's own spoken lines with a voice that runs on the phone, or stays silent.) *Ask* opens the Ask screen under the card's headline: type a question (or say it into the keyboard's microphone) and tap *Ask*. The answer is E03's recall from his own papers — in his density the lines of one thing (voice mode), in Mei's up to five (text) — each line under where it came from, the boundary last, and *Hear* reads it on tap; *Back to your cards* returns to the same card. *Family* sends a blood pressure or a visit card to the family thread by reference (checkpoint 13's thread shows it as a reading card); any other card says *Nura cannot send this card to your family yet.* *Not for me* writes his word back; the card says *Nura wrote down that this is not for you. / You will not see this kind of card again today.*, and the next pages have none of that kind today.

**At night.** Between 21:00 and 07:00 in Singapore the backend holds everything but a red flag; the feed says *Nura keeps quiet at night. / Your cards come back in the morning.* and shows no card. To see it at any hour, start the dev run on a frozen clock — `NURA_FROZEN_CLOCK=2026-09-14T22:30:00+08:00 make dev` — or move a frozen one with `POST /dev/clock {"at": "2026-09-14T22:30:00+08:00"}` at http://127.0.0.1:8000/docs (a dev run only; anywhere else the setting refuses to start and the route is not there).

**For the caregiver.** Sign in as Mei (a key from Pa, as in checkpoint 8) and open the same screen in the smaller look: no gate, the duty card instead, and under each card what became of it on Pa's page — *This was on the page Pa sees.*, *Pa opened this card.*, or, for the warfarin batch notice checkpoint 8 makes, *Nura kept this back from Pa.* A button her key does not open (the family thread, without the family part) is refused in one plain sentence, and the card stays.

**Offline, on the Mac.** `make build-web`, open http://127.0.0.1:8000/app/, reach Today and open the feed once. Go offline and reload: Today opens as in checkpoint 10; *See more for you* opens the feed on the first page the phone kept, under *Nura cannot reach the internet right now. / These are your cards from earlier today.* and the time it was read, with no spinner. The kept page is bound to the key that read it and good until midnight in Singapore; the next day, still offline, it is gone from the phone and Today shows only the emergency card. Sign out, a refusal, or switching papers deletes it with Today's page.

What you will see (the operator's walk: `make web-e2e`, with `make dev` serving the build):

```
✓ feed.spec.ts › the pager: one card a screen, in the backend's order, the gate, endless past it on stable cursors, nothing plays by itself
✓ feed.spec.ts › a learning card: its lines, its boundary, its why, four side actions; Hear on tap only, stopped when it leaves; Not for me holds the kind
✓ feed.spec.ts › Family sends a reading to the family thread by reference; a card it cannot carry says so; Ask opens and comes back to the same card
✓ feed.spec.ts › the caregiver's list: no gate, what was held from him shown as held, and a refusal said in one plain sentence
✓ feed.spec.ts › quiet hours (the clock pinned to 22:30): the pager says Nura keeps quiet, with no card and no spinner
✓ feed.spec.ts › Reduce Motion: the pager moves a card at once, with no smooth scroll
✓ feed.spec.ts › offline: the pager opens on the kept first page, dated, with no spinner; past midnight only the emergency card
```

Both clocks stand at 10:00 in Singapore on Monday 14 September for the whole run: the phone's by Playwright's clock, the backend's by `NURA_FROZEN_CLOCK` — `make web-e2e` starts `make dev` itself with it (`web/playwright.config.ts`, `webServer`), so the dose windows, the quiet hours and "today" are the same whenever and wherever it runs. The quiet-hours test moves the backend to 22:30 with `POST /dev/clock` and puts it back. Build first (`make build-web`) so the backend serves `/app`.

**What "passed" means.** One card fills the screen and the screen snaps to one card at a time, up and down only — nothing moves sideways, there is no pull-to-refresh and no swipe to dismiss; the order is the backend's; the gate is a card with *Keep going*, and past it the feed pages on for as long as you swipe, each page asked for once by the cursor the page before handed back; every card shows its lines, its why, and — on a learning card — the boundary it ends on, and carries the State it was rendered from; *Hear*, *Ask*, *Family* and *Not for me* are visible buttons on every card, at least 56 by 56; nothing speaks until you tap *Hear*, and it stops when the card leaves; *Not for me* holds that kind of card for the rest of the day; a refusal is one plain sentence; and offline the feed opens on the page the phone kept today, and not after midnight. If a step does not do that, tell the operator which one and what you saw instead.

## How to run checkpoint 22

Two parts: the API walk (`make checkpoint N=22`), and the Visit screen in the browser. Neither depends on another checkpoint having run. Four fresh numbers every run — Pa, his chief Mei, Kit with a viewer's key, Siti with a helper's — so it can be run again on the same `dev.db`.

```sh
make dev                # terminal 1: migrates dev.db (0022 adds consult_recording, consult_segment and the clip columns), serves on http://127.0.0.1:8000
make checkpoint N=22    # terminal 2: walks the API part, about three seconds
```

No audio is committed and no speech provider is called. The recording is a placeholder: the four bytes a webm opens with, a marker and a label (`backend/tests/consult_audio.py`). What the fixture transcriber hears in it is in `backend/tests/fixtures/voice/`; who spoke when is in `backend/tests/fixtures/speakers/`; the card is read from `backend/tests/fixtures/visits/consult-bp-review.json` — the in-room notice, Dr Tan's yes, the visit, Pa's question, Mei's word. The bytes go to the local object store under `backend/var/objects/SG/consults/`.

What you will see (the numbers, ids and days change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591222005) registered by phone code and signed in (the code read from the server log)
✓ Mei (+6592235931) registered by phone code and signed in (the code read from the server log)
✓ Kit (+6593247044) registered by phone code and signed in (the code read from the server log)
✓ Siti (+6594255528) registered by phone code and signed in (the code read from the server log)
✓ Lim (+6595265033) registered by phone code and signed in (the code read from the server log)
✓ Clinic (+6596273292) registered by phone code and signed in (the code read from the server log)
✓ Pa opened his profile: Mei his chief (every part), Lim a caregiver (the visits, the record, the readings), Kit a viewer (the visits, the readings), Siti a helper (the medicines), and the clinic (the visits, the record)
✓ Dr Tan in Pa's directory at Gleneagles Hospital, 6A Napier Road; the visit tomorrow, Wednesday 16 September at 9, on Pa's yes; Mei's note about the place ("parking at B2") and Mei on the roster tomorrow from 7 to 12
✓ Pa's blood pressure tablet from its label, and his hospital letter confirmed: both are things to bring
✓ GET …/appointments/{appt}/logistics: the card for tomorrow, from the record and State (state 4ce5d0ad…), every line through the plain-words verifier:
    [when  ] You see Dr Tan on Wednesday 16 September at 9 in the morning.
    [place ] Dr Tan is at Gleneagles Hospital, 6A Napier Road.
    [note  ] Mei wrote a note about getting to Dr Tan.
    [driver] Mei will tell you who is driving you to Dr Tan on Wednesday 16 September.
    [bring ] Bring your blood pressure book on Wednesday 16 September.
    [bring ] Bring your medicines in their boxes on Wednesday 16 September.
    [bring ] Bring your hospital letter on Wednesday 16 September.
             Mei's note: "parking at B2"  (as she wrote it)
    driver: suggested — Mei, on the roster then; needs the chief's yes: True
✓ the suggestion is nothing until a yes: without one, NotAConfirmerHere (400); Kit's viewer key does not reach the family list, so it cannot mint one, OutOfScope (403, family). Mei's yes (subject drive) made the task "drive Pa to Dr Tan", hers, due at the visit; the card now says: "Mei will drive you to Dr Tan on Wednesday 16 September."
✓ Mei's list (Pa's feed keeps quiet at night): the visit_logistics card the day before — "Getting to Dr Tan tomorrow", its lines the card's, rendered from state 4ce5d0ad…, no boundary (it infers nothing), never autoplayed
✓ no recording without Pa's agreement: the notice and the upload are both refused, ConsentWithheld (403), and nothing is kept; Kit's viewer key is refused before the room is told anything, NotTheirsToChangeVisits (403)
✓ Pa agreed to Nura listening (POST …/consents/recording); the notice Mei's phone says first, to Dr Tan by name:
    Nura will listen now.
    Nura keeps what you and Dr Tan say.
    Only you and the family you let in can hear it.
    Is that OK, Dr Tan?
    and on a no: Nura will not listen today. / Mei will write the notes by hand.
✓ Mei's recording, sent once on Stop (POST …/recording, audio/webm;codecs=opus, 66 s): a consult voice artefact 3c394484… on the RECORDING consent e77a7234…, heard at 0.93, and who spoke when — 11 stretches, no words in any row:
      0.0–8.6   unknown
      8.6–10.4  doctor  ← Dr Tan's yes, the first seconds after the notice
     10.4–19.8  doctor
     19.8–28.9  doctor
     28.9–36.2  doctor
     36.2–39.0  doctor
     39.0–47.5  doctor
     47.5–55.1  doctor
     55.1–59.3  patient
     59.3–63.0  doctor
     63.0–65.8  family
✓ the post-visit card from the transcript (summary 1c93f2aa…), each line with where in the recording Dr Tan said it:
     19.8–28.9  Ask Dr Tan about the new amount of the water pill (frusemide).
     28.9–36.2  Every morning, stand on the scale before breakfast.
     36.2–39.0  Every evening, eat a lighter dinner.
     39.0–47.5  You have a blood test on Monday 28 September.
     39.0–47.5  Eat nothing after 12 midnight on Sunday 27 September.
     39.0–47.5  Water is OK.
     47.5–55.1  Bring your blood pressure book on Thursday 15 October.
     47.5–55.1  You see Dr Tan again on Thursday 15 October at 10 in the morning.
     47.5–55.1  Mei will book it.
     10.4–19.8  Dr Tan wrote down your blood pressure.
✓ Mei asks "what did Dr Tan say about the water pill" before the card has a yes: "Your card from Dr Tan on Wednesday 16 September is waiting for your yes." — nothing Dr Tan said is cited yet
✓ Mei confirms the card on her yes, then asks again: "Dr Tan talked about this on Wednesday 16 September." — citing the recording 3c394484… from 19.8 to 28.9 seconds, the button "Hear what Dr Tan said"
✓ the clip (GET …/artifacts/{a}/clip?start=19.8&end=28.9): the recording's 47 bytes, audio/webm, X-Media-Fragment t=19.8,28.9 — the phone plays that stretch
✓ who hears it is what the room was told: Pa and the family he let in — Lim, his caregiver, hears the clip and the whole recording; Kit's viewer key and the clinic's key both hold the visits and are refused, OnlyTheFamilyHears (403); Siti's helper key does not reach the visits, OutOfScope (403); a stretch outside the recording is NotAClip (400)
✓ Pa reads his trail (500 lines); every refusal of this walk is on it:
    2026-09-14T19:17:25    Pa  read visits consult_recording  refused NotAClip
    2026-09-14T19:17:25  Siti  read visits consult_recording  refused OutOfScope
    2026-09-14T19:17:25  Clin  read visits artifact  refused OnlyTheFamilyHears
    2026-09-14T19:17:25   Kit  read visits artifact  refused OnlyTheFamilyHears
    2026-09-14T19:17:24   Kit  read visits consult_recording  refused NotTheirsToChangeVisits
    2026-09-14T19:17:24   Mei  write visits consult_recording  refused ConsentWithheld
    2026-09-14T19:17:24   Mei  read visits consent  refused ConsentWithheld
    2026-09-14T19:17:24   Mei  read visits consult_recording  refused ConsentWithheld
checkpoint 22 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 22 passed`. The criteria: the logistics card is composed from the record only — the time from the booking, his way; the place from the directory; the chief's note shown as she wrote it under her name, never as Nura's words; who drives from a family task naming this visit, or the roster's person on duty then as a suggestion that is nothing until the chief's yes, which makes the task "drive Pa to Dr Tan"; what to bring from his record — and every line passed the plain-words verifier and the card names its State; the feed carries it the day before and on the day; nothing records without the RECORDING consent in force, a key that does not change the visits is refused before the notice is given, and every refusal is on the trail; the recording is kept as a consult voice artefact in the region, on the consent it rested on, heard, split by speaker with times and no words in any row, and read into the post-visit card with each line's place in the recording; an answer about what the doctor said cites nothing from the recording until the card has his yes, and then cites it from its start to its end; the clip and the whole recording are heard only by him and the family he let in — his chief and his caregivers — and a viewer's key or a clinic's is refused in plain words, on his trail, however much of the visit it can read. If you see a ✗, the line says what was asked, what came back (status and body) and what was expected; tell the operator and paste the line.

**The Visit screen, on the Mac or the phone.** `make build-web`, then `make dev` serves the app at http://127.0.0.1:8000/app/ (or `make web` for http://127.0.0.1:5173/app/). Sign in with the number the walk printed for Pa. On Today, under *See more for you*, tap *See your next visit*. The screen is the logistics card, in the backend's words, with Mei's note under *Mei's note* and *Hear* to have it read. Under it is one big button, *Start recording*, and the line *Keep this page open while Nura listens.*

1. **Start recording.** On a profile that has not agreed yet, Pa reads today's words for Nura listening and taps *I agree*. Then the notice appears and is said out loud: *Nura will listen now. … Is that OK, Dr Tan?* The phone asks for the microphone once, and a red dot and a timer appear. The recording holds the notice and then Dr Tan's answer.
2. **Dr Tan said yes** keeps listening. **Stop** sends the recording once. The screen says *Nura kept the recording.* and shows the post-visit card. Under each line Dr Tan said is *Hear what Dr Tan said*, which plays only that stretch.
3. **Dr Tan said no** stops the microphone and throws the audio away on the phone. Nothing is sent. The screen says *Nura will not listen today. You will write the notes by hand.* and offers a box for the notes, read into the same card.
4. **Leave the page while it listens** (switch apps, or lock the phone): it stops at once. When you come back it says *Nura stopped listening when you left this page.* One tap, *Keep what Nura heard*, sends what it heard. A browser cannot keep listening in the background (ADR 0006).

The operator's walk of the screen is `make web-e2e` (`web/tests/e2e/visit.spec.ts`): the phone's clock and the backend's frozen at 10 in the morning on Monday 14 September, the recorder a stand-in that hands back the placeholder recording.

```
✓ tests/e2e/visit.spec.ts:32:1 › the visit screen: logistics from the record, the yes to a driver, consent, the notice first, one upload on Stop, the card with its clips
✓ tests/e2e/visit.spec.ts:127:1 › a no keeps nothing: the recorder stops, nothing is sent, and the notes are written by hand
✓ tests/e2e/visit.spec.ts:159:1 › the page hidden while listening stops at once, and what was heard is kept on the phone for one tap
```

## Rules the operator follows between checkpoints

- Stories merge when CI is green, the safety and plain-words reviewers pass, and the operator has read the diff. `risk:high` stories get a written note in the PR saying what was checked.
- A checkpoint is not declared ready until `make checkpoint` passes end to end on a clean database.
- Anything that needs a real credential (SMS provider, licensed drug data, WhatsApp BSP, Apple) is a fixture until you say otherwise; the checkpoint says so where it applies.

## How to run checkpoint 20

Delivery (E11): the trigger engine, the ladder, the morning ritual. It runs on a dev run's frozen clock (#118), so what the backend says about the hour does not drift with the hour you run it at: start the server with the clock standing at 06:00 on Monday 14 September, Pa's wall clock, and the checkpoint steps it (`POST /dev/clock`) to each hour it needs, running the engine there (`POST /dev/run-triggers`, the dev door onto `run_due`; a deployment's scheduler calls it every five minutes). Three fresh phone numbers every run — Pa, Mei, Siti — so it can be run again on the same `dev.db`.

```sh
NURA_FROZEN_CLOCK=2026-09-14T06:00:00+08:00 make dev    # terminal 1: migrates (0019 adds the delivery tables), a frozen clock
make checkpoint N=20                                     # terminal 2: about five seconds
```

What you will see (the numbers and ids change each run):

```
✓ the dev server answers at http://127.0.0.1:8112 (GET /health)
✓ Pa (+6591201072), Mei (+6592209219) and Siti (+6597207304) registered by phone code (the codes read from the server log)
✓ Pa opened his profile and agreed to WhatsApp; Mei (his daughter) holds a chief key and is on duty weekdays 6 in the morning to 11 at night; Siti holds a helper key (medicines, emergency, send)
✓ Pa added amlodipine 5 mg, one every morning, two tablets left (checkpoint 6's route), at 06:00 on 2026-09-14 by the dev run's frozen clock
✓ 07:20: nothing; 07:31, his breakfast (the one breakfast time, 07:30 until he says — the first week's prompt comes at the same moment): the morning card, the approved template (he has not written in 24 hours), once — 07:45 sends nothing. Pa (patient): sent by whatsapp, template morning_card; rule breakfast_anchor_reached. What he reads:
    → Good morning, Pa, this is Nura.
    → Today is Monday 14 September.
    → Take 1 tablet of your blood pressure tablet with breakfast.
    → Your blood pressure tablet runs out on Wednesday 16 September.
    → Ask your family to order more.
    → When you can, take your blood pressure.
    → Send me the 2 numbers.
✓ 08:31, the window closed untapped: rung 0, Pa — Pa (patient, rung 0): sent by whatsapp, template dose_reminder; rule dose_window_closed_untapped
    → Pa, this is Nura.
    → Have you had your blood pressure tablet with breakfast?
    → When you have, reply Taken.
✓ 09:01, nobody answered: rung 1, the helper — Siti (helper, rung 1): sent by whatsapp, template dose_check; rule dose_window_closed_untapped, in Malay:
    → Pa belum kata Sudah ambil untuk ubat tekanan darah Pa bersama sarapan.
    → Tolong tengok Pa.
    → Bila Pa sudah ambil, balas sudah beri.
✓ 09:31, still nobody: the third ask goes to the roster, not to him — Mei (on_duty, rung 2): sent by whatsapp, template dose_check; rule dose_window_closed_untapped
✓ Siti replied "sudah beri" on WhatsApp: the Taken tap was written for the breakfast tablet — on the medicines key she holds, on the WhatsApp channel — and the ladder stopped; 10:05 asks nobody. Her reply in the thread:
    → Terima kasih, saya sudah tulis.
    → Pa sudah ambil ubat tekanan darah Pa.
✓ 10:05, after his check-in time (10:00): the schedule handed the day's nudge over and delivery sent it — Pa (patient): sent by whatsapp, template nudge; rule nudge_handed_over; the web handing it over again as he answers (POST /nudges/plan) gives back the same nudge — one row (GET /nudges) — and 10:10 sends it no second time. What he reads:
    → Nura has a note for you.
    → Your blood pressure tablet is new since Monday 14 September.
    → How are you feeling today?
✓ 07:20, the first run of the day, the reorder date reached: Mei (on_duty): sent by whatsapp, template reorder_family; rule reorder_date_reached:
    → Pa's tablets are running low.
    → Pa's blood pressure tablet runs out on Wednesday 16 September.
    → Can you order more for Pa?
✓ 07:31, the same rule the second time that day: capped (once a day) — no second message, and no row at all on the runs after it
✓ Mei added Dr Tan and Gleneagles to his directory (POST /profiles/{id}/providers), Gleneagles marked as the hospital on his insurance (panel: true); Dr Tan's hours are not set, so his clinic answers 08:00 to 20:00
✓ 22:30, inside the quiet hours: a red flag, written first, went straight to the roster — on_duty, sent by whatsapp (red_flag_notice_hospital), category alert, never capped and never quiet; not to him. A fall is the same-day tier, and Dr Tan's clinic is closed at 22:30: never "call your doctor today" — the emergency department of the hospital on his insurance, named (E19-05). His reply:
    → This one we do not wait for.
    → Go to the emergency department at Gleneagles now.
    → Gleneagles is on your insurance.
    → If you cannot get there safely, call the ambulance now on 995.
    → Mei knows now.
    → Nura does not decide what is wrong.
✓ 22:36, nobody had answered: the next rung, still at night — Siti (key_holder, rung 4): sent by whatsapp, template red_flag_notice_hospital; rule red_flag_raised; nothing else went: a reminder waits out the quiet hours
✓ 07:30 the next morning, the flag still inside its day: today's top three (GET /profiles/{id}/feed/today) — alerts first, then reminders, then insights:
    [alert   ] This one we do not wait for — one action: call, on the stable wash. Why: This is one of the things we never wait for.
    [reminder] Your tablets today — one action: taken, on the stable wash. Why: You have medicines on your list.
    [reminder] Your blood pressure tablet is running low — one action: ask_to_order, on the stable wash. Why: You have about 1 day of your blood pressure tablet left.
✓ "Your tablets today" played as its spoken twin (GET …/feed/{item}/voice): audio/wav, 92044 bytes, 11.5 seconds, cache hit — the fixture voice is silence as long as the words take to say
✓ every attempt is on the delivery log with the rule that fired: breakfast_anchor_reached, dose_window_closed_untapped, nudge_handed_over, paper_waiting_for_a_yes, red_flag_raised, reorder_date_reached
✓ 07:40 on Tuesday 15 September, three days before his visit with Dr Tan on Friday 18 September: the pre-visit brief was rendered then and its card sent — Pa (patient): sent by whatsapp, template visit_brief; rule brief_three_days_before; 08:10 sends it no second time. What he reads:
    → Your next visit is on Friday 18 September.
    → You see Dr Tan at 10 in the morning.
    → This visit is about your blood pressure.
    → Bring your blood pressure book on Friday 18 September.
    → Nura prepared this from your papers.
    → This is not a doctor's advice.
    → Ask Dr Tan.
checkpoint 20 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 20 passed`. That is the whole of the criteria: the morning card goes at his breakfast — the one breakfast time his settings (E01), his routine's anchors (E10) and his first week's prompts all read, 07:30 until the family sets it — as the approved template, once a day; a tablet with no Taken by the end of its window asks him, then the helper, then whoever the roster puts on duty — the third ask goes to the roster, not to him — and a "sudah beri" on WhatsApp writes the Taken tap and stops the ladder; at his check-in time the schedule hands the day's planned nudge over — never in the quiet hours, never on a red-flag day — and delivery sends it once, the web's own handover giving back the same nudge (W7); a rule true all day (the reorder date) is said once, held for the quiet hours before 7 and by the cap after it, the hold written down once; a red flag goes straight to the roster at 22:30, never quiet and never capped, and not to him — and out of his doctor's hours (the directory's, else 08:00 to 20:00) a same-day flag never says "call your doctor today": it names the emergency department of the hospital marked as on his insurance (and the ambulance if he cannot get there safely), or the ambulance if it gets worse, while chest pain, the signs of a stroke and shaky-and-sweaty on a sugar medicine are the ambulance at any hour, and every reply ends "Nura does not decide what is wrong." (E19-05, ADR 0010); today's top three lead with the alert and every card says why; one card is played as its spoken twin, under thirty seconds; three days before a visit, after his breakfast, the pre-visit brief is rendered and its card sent once, under the cap on briefs a day (E05-01). Every attempt is a `Delivery` row naming the rule that fired (`GET /profiles/{id}/deliveries`, the owner's and his chief's). If you see a ✗, the line says what was asked, what came back and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with the profile id and tokens from it:

1. **Change the channel for a type.** As Pa, `PUT /profiles/{profile_id}/delivery-settings` with `{"channels": {"reorder": ["whatsapp"]}, "caps": {"reorder": 2}}`; the next day's reorder goes by WhatsApp only, and twice before the cap holds it. `{"caps": {"flag": 3}}` is refused: an alert is never capped.
2. **Hear a card.** `GET /profiles/{profile_id}/feed/{item_id}/voice` for any card on his feed: `audio/wav`, `X-Duration-Seconds` under 30, `X-Voice-Cache: hit` the first time already — a card's audio is said and kept when the card is made, under its voice script's digest (E22-03), so the first play is a read; `?language=ta` is a 404 (Tamil comes at T2) and the web client says it with the phone's voice.

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

## How to run checkpoint 15

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having run. Three fresh phone numbers every run — Mei, Pa, Kit his son — so it can be run again on the same `dev.db`. The read-back is answered the way the web's one-thing-a-screen onboarding does it: one line on its own, then the rest. The papers are the two redacted samples of checkpoint 5 (`backend/tests/fixtures/paper/`), sent as their placeholder bytes; nothing is a real photo and no model is called.

```sh
make dev                # terminal 1: migrates dev.db (0015 adds the onboarding tables), serves on http://127.0.0.1:8000
make checkpoint N=15    # terminal 2: walks the whole scenario, a few seconds
```

To see the first morning of his week come due, start the server on a frozen clock (#118): `NURA_FROZEN_CLOCK=2026-09-15T16:00:00+08:00 make dev`. The walk reads the server's clock (`GET /dev/clock`), moves it to 07:30 the next morning (`POST /dev/clock`) and asks what is due. On the wall clock it asks with `?at=` instead.

What you will see (the numbers, ids and dates change each run; the words are in Pa's language, Malay; the first week starts tomorrow on his clock):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ the server's clock reads 2026-09-15T01:24+08:00 in Singapore (frozen, NURA_FROZEN_CLOCK; the walk moves it with POST /dev/clock)
✓ Mei (+6594445772) registered by phone code and signed in (the code read from the server log)
✓ Mei set up a profile for Pa (+6593339308) as he asked: she is its steward
✓ the word cloud answers without signing in (GET /onboarding/conditions?language=ms): 20 words first, 68 in all, in Malay — Darah tinggi, Kolesterol tinggi, Kencing manis, Sakit jantung, Masalah buah pinggang …
✓ Mei opened the biography (POST /profiles/{id}/biography): step about_you, next save_settings; the words of the step, in Pa's Malay:
    Sedikit tentang anda
    Beritahu kami bahasa yang anda paling suka.
    Tekan apa-apa yang berkaitan dengan kesihatan anda.
    Ini hanya supaya Nura tahu apa yang perlu diberi perhatian.
✓ Mei saved Pa's settings (PUT /profiles/{id}/settings): Malay, simple, large text, voice on, breakfast 07:30, Dr Tan, and 5 conditions — Darah tinggi, Kolesterol tinggi, Kencing manis, Masuk hospital tahun lepas, Ubat cair darah
✓ State took them at once — snapshot 19: spoken and reading language ms, format density simple and preferred voice (the fact the feed goes voice-first on), vision large_text true, setting.birth_decade 1950 (the age band lab trends read), each a fact with Mei's yes on the event of the save; the profile's own language is ms
✓ Mei added the lipid report (POST …/biography/papers, paper lab_result): a review card of 7 fields, ldl and triglycerides dotted; the biography waited on it (next confirm_cards), and one tap confirmed it with triglycerides corrected to 54
✓ Mei added the warfarin label (paper medicine): read as a medicine_label marked anticoagulant, and confirmed with one tap from its label photo
✓ the biography is at the read-back: 12 lines, each a confirmed fact, in Malay:
    Ini yang Nura faham
    Anda beritahu kami: Darah tinggi.
    Anda beritahu kami: Kolesterol tinggi.
    Anda beritahu kami: Kencing manis.
    Anda beritahu kami: Masuk hospital tahun lepas.
    Anda beritahu kami: Ubat cair darah.
    Doktor anda ialah Dr Tan.
    Kolesterol anda 230 pada Khamis 7 September 2023.
    Kolesterol baik anda 73 pada Khamis 7 September 2023.
    Kolesterol jahat anda 152 pada Khamis 7 September 2023.
    Label ini untuk ubat cair darah anda, Warfarin.
    Label ini menyebut 1 biji sekali sehari waktu malam.
    Label ini kata Dr Lim yang beri ubat ini.
✓ Mei said no to "Kolesterol jahat anda 152 pada Khamis 7 September 2023." on its own (one line, one screen), then yes to the other 11 at once — a dispute (c0fc1d0f…) opened beside the fact, which still holds (152, from the photo, confirmed by Mei): nothing anyone confirmed is overwritten
✓ the questions the papers raised, in Malay (step questions):
    Beberapa soalan tentang surat-surat anda
    Mei akan lihat surat itu sekali lagi.
    Adakah anda periksa tekanan darah di rumah?
    Adakah anda ada surat hospital anda?
    Bila ujian gula anda yang terakhir?
    Bila ujian buah pinggang anda yang terakhir?
    3 lagi boleh tunggu kemudian.
✓ Mei kept two of them (POST …/biography/questions): bp_numbers, discharge_letter — no visit yet, so they wait on the sitting for the first one booked
✓ Mei closed the biography: 2 papers, 13 facts, 1 disputed; the summary, in Malay:
    Nura simpan 2 surat anda.
    Nura catat 13 perkara daripada surat-surat anda.
    Anda kata satu baris tidak betul.
    Mei akan lihat surat itu sekali lagi.
    Esok waktu sarapan, Nura akan minta satu perkara lagi.
    Ada 7 perkara untuk diminta, satu setiap hari.
    Halaman Hari Ini anda datang daripada apa yang anda beritahu kami.
✓ Mei booked a visit with Dr Tan on 2026-10-01 (POST …/appointments): the two questions she kept on Day 0, when there was no visit, went on its list in the same request (E05, GET …/appointments/{id}/questions), and the sitting names the visit:
    Adakah anda periksa tekanan darah di rumah?
    Adakah anda ada surat hospital anda?
✓ Pa (+6593339308) registered by phone code and signed in (the code read from the server log)
✓ Pa claimed the profile with his OK: he is its owner, Mei his chief
✓ Pa reads his first week (GET /profiles/{id}/plan): 7 prompts, one a day from tomorrow, 2026-09-16, at 07:30 on his clock (Asia/Singapore); nothing is due yet:
    day 1  2026-09-16T07:30  pending  Nombor tekanan darah biasa anda — Hari ini, ambil gambar mesin tekanan darah anda.
    day 2  2026-09-17T07:30  pending  Surat hospital anda — Hari ini, ambil gambar surat hospital anda.
    day 3  2026-09-18T07:30  pending  Ujian gula anda yang terakhir — Hari ini, ambil gambar mana-mana ujian darah.
    day 4  2026-09-19T07:30  pending  Ujian buah pinggang anda yang terakhir — Hari ini, ambil gambar mana-mana ujian darah.
    day 5  2026-09-20T07:30  done     Lawatan anda yang seterusnya ke Dr Tan — Hari ini, ambil gambar kad temu janji anda.
    day 6  2026-09-21T07:30  pending  Lawatan terakhir anda ke Dr Tan — Hari ini, ambil gambar slip lawatan terakhir anda.
    day 7  2026-09-22T07:30  pending  Kad insurans anda — Hari ini, ambil gambar kad insurans anda.
✓ tomorrow at 07:30 exactly one prompt is due (bp_numbers); Pa said Later to the insurance card (POST …/plan/later): it goes to the back of the week, asked once more on 2026-09-23 at 07:30; a second Later would retire it
✓ Pa's State shows his settings: cognitive (language ms, density simple, voice), functional (large text), preference (breakfast 07:30, called Pa), and the five conditions he told in the clinical dimension, as told — no posture moved (posture stable, reading language ms)
✓ Kit (+6595557536) registered by phone code and signed in (the code read from the server log)
✓ Kit, his caregiver, reads the settings whole (a key to the record opens the conditions and the doctor); changing them is refused: NotTheirsToSetUp (403), and it is on Pa's trail
checkpoint 15 passed: every step did what docs/checkpoints.md says
```

What each part rests on: the settings are `app/onboarding/settings.py` (who reads which part, and the subjects State folds them under, are in its docstring); the steps of the sitting, the read-back and the dispute are `app/onboarding/biography.py`; the questions and the plan's gaps are `app/onboarding/gaps.py` (the part of docs/gaps-and-unlocks.md this backend can act on); the first week and `due_prompts` are `app/onboarding/plan.py`; every line he reads is in `app/onboarding/strings.py` and is checked by `app/onboarding/words.py` as it is served.
## How to run checkpoint 14

Two terminals, as before. Checkpoint 14 is a module of its own (`backend/scripts/checkpoints/cp14.py`); `make checkpoint N=14` dispatches to it.

```sh
make reset-db           # optional: a clean local database (stop `make dev` first)
make dev                # terminal 1
make checkpoint N=14    # terminal 2, about three seconds
```

It registers Pa, Mei (chief), Lin (a neighbour with an emergency-only key) and Kit (no key) on fresh numbers, adds the water pill from a label photo and a blood pressure, puts his insurer on the card on his yes, then walks the three stories: the emergency card as JSON and as the printable page — in his language and, when that is not English, with every line's English twin for the ambulance crew — (open the URL it prints in a browser with Pa's token, or print it); the not-feeling-well button with "tired today" typed and "chest pain" said by voice (a placeholder voice note the fixture transcriber knows by digest, `backend/tests/fixtures/voice/`; his own note, kept like typed text, ADR 0003); the symptom log by voice; and Kit refused. Every what-to-do card opens with the boundary's reassurance and ends on "Nura does not decide what is wrong." (E13-02, E16, `app/safety/boundary.py`). The voice notes and the typed words are kept as artefacts in `backend/var/objects/SG/voice/` and `words/`; no row holds his words.

What you will see (the phone numbers, ids and dates change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591116946) registered by phone code (no SMS; the six digits read from the server log) and signed in
✓ Pa opened his own profile (wording 1, in the app)
✓ Mei (+6592221831) registered by phone code (no SMS; the six digits read from the server log) and signed in
✓ Lin (+6594448471) registered by phone code (no SMS; the six digits read from the server log) and signed in
✓ Kit (+6593339060) registered by phone code (no SMS; the six digits read from the server log) and signed in
✓ Pa let Mei, his daughter, in to everything and cut her the chief key
✓ Pa let Lin, a neighbour, in to the emergency card only and cut her an emergency key (scopes: emergency, profile)
✓ Pa added the water pill (frusemide 40 mg, 1 tablet every morning) from a label photo, with his OK, and tapped Taken
✓ Pa typed in a blood pressure (138 over 84): a reading event and a fact resting on it
✓ Pa typed his insurer (Great Eastern, policy GE-4471-0932) on his yes (subject insurer, PUT /profiles/{id}/emergency-card/insurer); Lin, with the emergency card only, cannot set it (NotTheirsToSetInsurer, 403), and an identity-card number is refused as a policy reference (NotAPolicyReference, 400)
✓ Pa read his emergency card (GET /profiles/{id}/emergency-card): the water pill with its strength and how much, Mei's name and number, his insurer (the policy reference as data, never in a sentence), the last blood pressure's date, 995 for Singapore, rendered from State 96032bf8… and written down as render ed18fadb…; the lines, every one verified:
    This is Pa's emergency card.
    Show this card to the doctor or the ambulance crew.
    Pa speaks English.
    Nura has no note of a condition for Pa.
    Pa takes the water pill (frusemide).
    Pa takes 1 tablet every morning.
    Pa has no allergy that Nura knows of.
    Mei looks after Pa.
    Call Mei first.
    Pa's insurance is with Great Eastern.
    The ambulance number is 995.
    Pa's blood pressure was last written down on Tuesday 15 September.
    This card is not a doctor's advice.
✓ Pa opened the printable page (GET /profiles/{id}/emergency-card.html): one self-contained page — no script, no stylesheet, no image fetched — paper surface, Ink #2B2733 on white, 20px body, the strength and the phone number as data beside the sentences; its first lines:
    http://127.0.0.1:8000/profiles/4d929951-3433-4bca-84cb-7dc67525d77b/emergency-card.html
    This is Pa's emergency card.
    Show this card to the doctor or the ambulance crew.
    Pa speaks English.
    Nura has no note of a condition for Pa.
    Pa takes the water pill (frusemide).
    Pa takes 1 tablet every morning.
✓ Mei read the card with her chief key (render 6788fd95…), and Lin read it with her emergency-only key — the same lines, the insurer included, stamped with the same State: an emergency key opens the card's fixed projection and nothing else, and is refused a stale card; the policy reference is his and his chief's in full, and the last four for Lin (••••0932)
✓ Lin read the card in Chinese (GET …/emergency-card?language=zh): every line with its English twin under the same id (13 lines), on the JSON and on the printable page (`<p class="twin" lang="en">`), so the ambulance crew reads what he reads; the first three:
    这是Pa的紧急卡。  /  This is Pa's emergency card.
    请把这张卡给医生或救护人员看。  /  Show this card to the doctor or the ambulance crew.
    Pa说英语。  /  Pa speaks English.
✓ Pa pressed the button and typed "tired today" (POST /profiles/{id}/not-feeling-well): his words kept as an artefact, a SYMPTOM event and a symptom fact resting on it, no red flag, the water pill already taken — so the card says rest, Mei is told (notice to 2 people), and a check-in is written for 2026-09-14T18:10:36.748662Z:
    Mei knows now.
    Sit down and rest now.
    Mei will call you today.
    Nura will ask you again in 2 hours.
    Nura wrote down how you feel.
    This is not a doctor's advice.
    Ask your doctor.
    Nura does not decide what is wrong.
✓ Pa pressed the button and said "chest pain" (a voice note through the fixture transcriber, heard at 0.94, kept as his own note): the flag was written first (85280904…), the posture is ACT, the ladder asked Mei first (E11-06, the one record of who is told; Lin five minutes on if nobody answers); the card, read aloud — who knows, the calls, and one closing line, never "Ask your doctor." after 995:
    Mei knows now.
    Call the ambulance now on 995.
    After that, call Mei.
    Nura does not decide what is wrong.
✓ State's posture is act (GET /profiles/{id}/state): the wash on his screen shifts to coral
✓ Pa logged a symptom by voice (POST /profiles/{id}/symptoms): "dizzy, quite a lot, since this morning" heard as dizzy, severity 2 (quite bad), since this morning; a SYMPTOM event and a fact with a seven-day window, his words kept in the voice note
✓ Mei read the symptom log (GET /profiles/{id}/symptoms) in plain words, with the day's name:
    Pa felt tired on Tuesday 15 September.
    It started this morning.
    Pa wrote this down.
    Pa felt chest pain on Tuesday 15 September.
    Pa said this out loud.
    Pa felt dizzy on Tuesday 15 September.
    It was quite bad.
    It started this morning.
    Pa said this out loud.
✓ Kit, with no key, was refused the card and the button: NoKey (403), in words that name nobody
checkpoint 14 passed: every step did what docs/checkpoints.md says
```

What to look at by hand: `GET /profiles/{id}/emergency-card.html` in a browser (Pa's or Lin's token as a bearer header, or from the web client once W1 lands) — one page, paper on mist, 20px, no request leaves for anything; `GET /profiles/{id}/state` after "chest pain" — `posture: act`, the situational dimension carrying `feeling.control = act` for 24 hours; `GET /profiles/{id}/audit` as Pa — the SYMPTOM `event` write, then the `red_flag` write, before the `delivery_ladder`, `fact` and `what_to_do_card` writes of that press, and Lin's `emergency_card` reads under scope `emergency`.

## How to run checkpoint 16

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having run. Two fresh phone numbers every run, Pa and Mei, so it can be run again on the same `dev.db`. Pa is set up in English so every line can be read here; the anchors, what changed and the answers come in Malay and Chinese for a profile in those languages. No model is called: which parts of the record a question is about is decided by the keyword retriever behind its port (`app/search/retrieve.py`), and every line of an answer is a template filled with the values of what it cites.

```sh
make dev                # terminal 1: migrates dev.db (0016 adds attachment, provider_note, last_looked), serves on http://127.0.0.1:8000
make checkpoint N=16    # terminal 2: walks the whole scenario, about three seconds
```

What you will see (the numbers, ids and days change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ Pa (+6591117507) registered by phone code and signed in (the code read from the server log)
✓ Pa's record: Dr Tan in his directory (POST /providers); the chest infection open (POST /episodes); two blood pressures, 146/90 six days ago and 138/84 yesterday during the illness; a check-up with Dr Tan ten days ago, confirmed then attended — each step on its own yes (POST /confirmations, subjects appointment and appointment_status); and a visit to Dr Tan in a week, inside the illness
✓ Pa added amlodipine 5 mg from the label photo (POST /medicines with the label and his yes): the label names Dr Tan
✓ Pa's lab paper read and confirmed: 7 facts resting on the photo 47e35e79…, dated on the paper
✓ GET /profiles/{id}/timeline: the three anchors of the spine, in his words with the day, then the first page newest first — the visit to come, then the illness with the reading taken during it — and the cursor to the check-up:
    Your last check-up was with Dr Tan on Friday 4 September.
    Your last visit was to Dr Tan on Friday 4 September.
    Your next visit is to Dr Tan on Monday 21 September.
    [appointment] 2026-09-21  Dr Tan  (0 papers, 0 events, 0 facts)
    [episode    ] 2026-09-14  chest infection  (0 papers, 1 events, 1 facts)
    [appointment] 2026-09-04  Dr Tan  (0 papers, 0 events, 0 facts)
✓ Mei (+6592226252) registered by phone code and signed in (the code read from the server log)
✓ Pa agreed to let Mei, his daughter, in and cut her a chief key; Mei put the lab photo with the chest infection on her own yes (POST /episodes/{e}/attach, subject attach) — the illness now holds 1 paper, 1 event and 8 facts, and the visit to come (1)
✓ the providers directory (GET /providers): Dr Tan — 2 visits; Dr Tan's history: 2 visits, 1 paper (through the illness), 1 medicine on his name, and Mei's note "parking at B2" — the chief's alone; a note naming a medicine was refused, NoteNamesHealth (400), and nothing of it was kept
✓ Mei's first look at what changed (GET /changes, 14 lines):
    This is your first look at what changed.
    A visit to Dr Tan is booked for Friday 4 September.
    The visit to Dr Tan on Friday 4 September happened.
    A visit to Dr Tan is booked for Monday 21 September.
    Your blood pressure tablet was added on Monday 14 September.
    A new blood pressure was written down on Monday 14 September.
    A new cholesterol test was written down on Monday 14 September.
    A new photo came in on Monday 14 September.
    Something new going on was written down on Monday 14 September.
    A paper was put with your visit or your illness.
    Mei was given a key on Monday 14 September.
    A new agreement was written down on Monday 14 September.
    A new agreement was written down on Monday 14 September.
    Mei wrote a note about Dr Tan on Monday 14 September.
    (still waiting) One tablet today is not taken yet.
✓ Pa added 132/80; Mei's second look counts from her first and says only that: "A new blood pressure was written down on Monday 14 September." (fact 61671c7c…)
✓ Pa asked by voice, "what was my blood pressure" (POST /ask, mode voice): one line, citing fact 61671c7c…, event af919e06…, then the boundary; what he hears:
    Your blood pressure on Monday 14 September was 132 over 80.
    Nura looked in your papers.
    This is not a doctor's advice.
    Ask Dr Tan.
✓ Mei asked in text, "what did Dr Tan say": every line cites what it rests on:
    Your next visit is to Dr Tan on Monday 21 September.  (appointment 5c9daed6…, provider 5bc91eeb…)
    Dr Tan gave you your blood pressure tablet.  (medication_line 6b841f61…, fact a0afbb9c…, artifact eb36403a…)
    Your cholesterol test from Thursday 7 September is in your papers.  (artifact 47e35e79…, attachment f3aa927d…, fact 729f907d…, fact 972c5be0…, fact 92c5ce1f…, fact 3eb8cbcc…, fact 4e2eba60…, fact b8de3795…, fact f05d541e…)
    You saw Dr Tan on Friday 4 September.  (appointment 240be989…, provider 5bc91eeb…)
    Nura looked in your papers.
    This is not a doctor's advice.
    Ask Dr Tan.
✓ "do I have cancer": nothing on the record answers it, so nothing is guessed:
    Nura does not have that written down.
    Ask Dr Tan.
    Nura looked in your papers.
    This is not a doctor's advice.
    Ask Dr Tan.
✓ Pa reads his trail (374 lines): Mei's refused note by name, the three asks — each naming the question kept as a message by reference, never its words — and Mei's two looks
checkpoint 16 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 16 passed`. The criteria: the timeline opens on the three anchors of the spine — the last check-up, the last visit, the next visit — each a whole line in his words with the day and the date, then the visits and illnesses newest first, each with what hangs off it, paged by a cursor that answers the same page twice; every visit names its provider, and an illness groups the visits and the events that were part of it (`?episode=` narrows the page to it); a paper hangs off an illness or a visit only on a person's yes for exactly that, in that person's name — or under the card's own yes when a review card is confirmed into an open illness; the providers directory shows each provider's visits, the papers from them and the medicines on its name, and the chief's note about the place, which only the owner and his chief can read or write and which is refused when it names a medicine or a condition; what changed counts from the reader's own last look, says what is new part by part with the ids beside each line, says what is still waiting, and a second look says only what came after the first; an answer is made only of templates and the values it cites, every line citing ids on this profile, voice gives one thing and text a few, a question nothing answers gets "Nura does not have that written down." and never a guess, and the boundary is last on every answer; every question is kept as a message by reference and every ask, look and refusal is on the trail. If you see a ✗, the line says what was asked, what came back and what was expected; tell the operator and paste the line.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token and the profile id:

1. **A part kept "only me".** Mark the readings only me (`POST /profiles/{profile_id}/confirmations` with `{"subject": "only_me", "scope": "readings"}`, then the only-me route from checkpoint 13), then as Mei `GET /profiles/{profile_id}/timeline`: `withheld` names `readings`, the illness loses the blood pressure and the moment it was taken, and `POST /profiles/{profile_id}/ask` with "what was my blood pressure" answers "Nura does not have that written down." with `readings` withheld. Pa himself still sees it all.
2. **A question that would change treatment.** As Pa, `POST /profiles/{profile_id}/ask` with `{"question": "should I stop my blood pressure tablet"}`: the answer says what is written down ("Dr Tan gave you your blood pressure tablet.") and then "Ask Dr Tan before you change any medicine." — never an instruction — with the boundary last.

## How to run checkpoint 19

Checkpoint 19 is Nura on your phone over https, from a demo deployment in Singapore
(ADR 0008). The whole runbook is `docs/deploy.md`; in short:

1. Create the hosting account yourself (Render recommended; Fly.io the alternative) — `docs/deploy.md` §4 (Render) or §5 (Fly.io) creates
   the app, the Postgres and the secrets in Singapore and deploys. Choose the demo's six-digit
   login code (`NURA_DEMO_LOGIN_CODE`) and keep it.
2. `https://<the address>/health/ready` answers `{"status":"ok"}` and `/api/deployment`
   answers `{"region":"SG","demo":true}`.
3. On the phone: open `https://<the address>/app/` in Safari, **Share → Add to Home Screen**,
   open it from the home screen, and sign in with `+65 0000 0001` and the demo code. The banner
   "Demo — not for real health information" is at the top of every screen, in the language
   the phone speaks.
4. A real number (`+65 9…`) is refused with "This demo only takes test phone numbers."
   Over https the offline worker installs as well (checkpoint 10 could not show it on the
   Wi-Fi address): after one visit, the home-screen app opens with the phone in flight mode.
5. From the laptop, the backend checkpoints walk against the same address:
   `cd backend && NURA_BASE_URL=https://<the address> NURA_DEMO_LOGIN_CODE=<the code> python3 -m scripts.checkpoint 2`
   — and 3–6, 14, 16, 17, 18 and 21 the same way (7, 8, 9, 13 and 15 need a laptop's dev run).
6. The next morning, after 03:00 Singapore time, the demo is empty again: your test account is
   gone, and signing in makes a new one.

## How to run checkpoint 21

Two terminals, as before. Checkpoint 21 is a module of its own (`backend/scripts/checkpoints/cp21.py`); `make checkpoint N=21` dispatches to it.

```sh
make reset-db           # optional: a clean local database (stop `make dev` first)
make dev                # terminal 1
make checkpoint N=21    # terminal 2, about two seconds
```

It registers Pa (in Malay) and Mei (his chief) on fresh numbers; Pa puts Dr Tan in his directory and a visit with him the day after tomorrow at 10, on his own yes (E03's routes); adds amlodipine from a label photo with his OK, taps Taken once, and types in a blood pressure. Then the feeling cloud, a tap and its one question, the note, a red word, the nudge plan, the metrics and the Me page. The dates in the lines are the day you run it.

What you will see (the phone numbers, ids and dates change each run):

```
✓ the dev server answers at http://127.0.0.1:8113 (GET /health)
✓ Pa (+6597119950) registered by phone code (no SMS; the six digits read from the server log)
✓ Mei (+6597222932) registered by phone code (no SMS; the six digits read from the server log)
✓ Pa opened his profile in Malay, let Mei, his daughter, in to everything and cut her the chief key
✓ Pa has Dr Tan in his directory (POST /providers) and a visit with him on Thursday 17 September at 10, written down on his own yes (POST /confirmations subject appointment, POST /appointments)
✓ Pa added amlodipine 5 mg from a label photo with his OK (POST /medicines, the label naming Dr Tan), tapped Taken once, and typed in a blood pressure (138 over 84)
✓ the cloud in Malay (GET /feelings/cloud?language=ms) is on Today because State changed, rendered from State 9cd60462…; the question, then the words biggest first — each with its reason code, kept for the audit and never shown to him:
    Ubat tekanan darah anda baru sejak Selasa 15 September.
    Apa rasa anda hari ini?
    Pening                 weight 3  base, new_medicine (amlodipine, monograph rule dizzy_standing)
    Buku lali bengkak      weight 3  new_medicine
    Letih                  weight 1  base
    Sakit                  weight 1  base
    Sesak nafas            weight 1  base
    Sedih                  weight 1  base
    Risau                  weight 1  base
    Susah tidur            weight 1  base
    Sakit dada             weight 1  base
    Sihat hari ini         weight 1  base
✓ Pa tapped Pening (POST /feelings): a SYMPTOM event in his word, and one question back — "Bila ia bermula?" — with Hari ini, Sejak semalam, Beberapa hari, Seminggu atau lebih
✓ Pa answered Sejak semalam (POST /feelings/{tap}/answer): the tap read against his medicines, his blood pressure and this week — the new medicine's licensed monograph lists dizziness — into a note kept for the visit, rendered from State 9cd60462…, read aloud as: headline, two things to tell Dr Tan, who does the next thing, and the boundary last:
    Perkara untuk diberitahu kepada Dr Tan
    Beritahu Dr Tan bahawa anda rasa pening sejak semalam.
    Ini boleh berlaku kerana ubat tekanan darah anda, yang baru sejak Selasa 15 September.
    Nura akan simpan ini untuk lawatan anda ke Dr Tan.
    Nura perasan ini daripada apa yang anda rasa.
    Ini bukan nasihat doktor.
    Tanya Dr Tan.
✓ the strip is gone after his tap (show false, tapped_today), and stays gone until State changes again
✓ Pa tapped Sakit dada: the red-flag path before anything else — the moment, the flag (de0fa8eb…, kept), Mei told, a notice to his emergency list and the ladder (a2f050fb…) for delivery — then the not-feeling-well button's whole flow, server-side: the what-to-do card (urgent, card a8a67205…) and the day's posture act (GET /state); no question, and no note (GET /feelings/notes still holds only the one for dizzy); the card he is shown:
    Mei sudah tahu.
    Hubungi ambulans sekarang di talian 995.
    Selepas itu, hubungi Mei.
    Nura tidak menentukan apa masalahnya.
✓ no nudge today (GET /nudges/plan): a red flag was raised today, so nothing is planned for it
✓ tomorrow's plan (GET /nudges/plan?day=2026-09-16): one nudge — anticipation, the visit the day after — no earlier than 10:00 on his wall, cap class one, with why; held, and said so: recognition (one_a_day):
    Anda berjumpa Dr Tan esok, Khamis 17 September.
    Sila bawa buku tekanan darah anda.
    [why] Anda nampak ini kerana lawatan anda esok.
✓ the nudge was written down and handed to delivery (POST /nudges/plan: nudge d3cfa8b1…, rendered from State 83fe6882…; nothing sent from here — E11 sends), and Pa accepted it (POST /nudges/{id}/response: an ENGAGEMENT event and a row)
✓ Mei, his chief, read the metrics (GET /nudge-metrics): week 2026-W38 — 2 taps on the cloud, 0 of them Fine today (share 0.0), anticipation handed over 1, accepted 1 (acceptance 1.0); no word he tapped, no line, no id in the answer
✓ Mei's metrics read is on Pa's trail (GET /audit): a read of nudge_metrics, in her name
✓ Pa's Me page (GET /me-summary): the days with a tablet taken, counted by the backend, in his words:
    Nura mengira 1 hari ubat anda sudah diambil.
    Nombor ini hanya naik.
checkpoint 21 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 21 passed`. The criteria: the cloud is on Today only after a change and goes after a tap; its words are weighed from State — "Pening" first because the new medicine's licensed monograph lists `dizzy_standing`, never because of a word Nura made up — and every word carries its reason code, which the client never shows; a tap asks one thing back from a fixed table; the note has at most two things to tell Dr Tan, each naming what it rests on, then who does the next thing, and ends on the boundary line for a feeling inference (E16); a red word presses the not-feeling-well button for him, server-side (E13/E14: the moment and the flag first, kept; a notice to his emergency list; the ladder; the day's posture act; the urgent what-to-do card, which is what he is shown) and makes no note; there is no nudge on a day with a red flag, and tomorrow's plan has one nudge, no earlier than his check-in time and never at night, with the rest held and said so; the metrics are counts with no word, line or id in them, for the owner and his chief only, and the read is on his trail; the Me page says the proud number (W1's) in his words, with no streak.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with Pa's token and the profile id:

1. **A yes that makes a word red.** `POST /profiles/{profile_id}/feelings` with `{"word": "breathless"}`: the one question is "Adakah ia berlaku walaupun anda duduk diam?". Answer it `{"answer": "yes"}` at `POST /profiles/{profile_id}/feelings/{tap_id}/answer`: a flag for breathlessness at rest, the family told, `opens: not_feeling_well`, and `note: null`.
2. **Two ignored of a kind.** Hand a day's nudge over (`POST /profiles/{profile_id}/nudges/plan?day=…`) on two days and touch neither; on the third, `GET /profiles/{profile_id}/nudges/plan` holds that kind as `resting_after_two_ignored` for a week, and `GET /profiles/{profile_id}/nudge-metrics` shows the ignored streak.

## How to run checkpoint 23

The same two terminals as checkpoint 2; it does not depend on any other checkpoint having run. Four fresh phone numbers every run — Pa, Mei, Kit, Aminah — so it can be run again on the same `dev.db`. The pharmacist is the one staff member `make dev` puts on `NURA_REVIEW_STAFF_TOKENS` (`pharmacist:nura-dev-pharmacist-token-0001`, a laptop's token that refuses to start anywhere but a dev run); the checkpoint reads the same token from `NURA_REVIEW_STAFF_TOKEN` if you set another. It reads the feed as if it were ten in the morning (`?at=`, as checkpoint 8 does), because the feed keeps quiet at night. No model, translation service or speech provider is called: the voice script is a function of the card's verified lines (`app/language/voice_script.py`), and audio is E11's.

```sh
make dev                # terminal 1: migrates dev.db (0021 adds review_item), serves on http://127.0.0.1:8000
make checkpoint N=23    # terminal 2: walks the whole scenario, about ten seconds
```

What you will see (the numbers, ids and counts change each run):

```
✓ the dev server answers at http://127.0.0.1:8000 (GET /health)
✓ make language: 3429 strings, 1176 keys in 22 catalogues (backend and web), 0 failures, 89 notes — the notes are consent words and WhatsApp templates, which change only as a new version: follow-ups, not failures
✓ “This one we do not wait for.” is one line in each language on the card, the reply and the notice (channels/safety_strings, delivery/strings, whatsapp/strings):
    Malay: Yang ini kita tidak tunggu.
    Chinese: 这个我们不等。
✓ Pa (+6592239311) registered by phone code and signed in (the code read from the server log)
✓ Mei (+6592243454) registered by phone code and signed in (the code read from the server log)
✓ Pa (144/87, Mei holds a key): every card on his feed carries its voice script, computed from its verified voice lines — the reading card is said:
    Your blood pressure today was one hundred and forty-four over eighty-seven.  ⟨500 ms⟩
    It is in your blood pressure book.  ⟨500 ms⟩
    Mei can see it too.  ⟨500 ms⟩
✓ the learning card pauses longer before the boundary it ends on:
    This comes from HealthHub.  ⟨1200 ms⟩
    Nura explains one thing in simple words.  ⟨500 ms⟩
    This is not a doctor's advice.  ⟨500 ms⟩
    Ask your doctor.  ⟨500 ms⟩
✓ Kit (+6592259126) registered by phone code and signed in (the code read from the server log)
✓ Kit's card in Chinese: “您今天的血压是144比87。” is said “您今天的血压是一百四十四比八十七。”
✓ Aminah (+6592269515) registered by phone code and signed in (the code read from the server log)
✓ Aminah's card in Malay: “Tekanan darah anda hari ini 144 atas 87.” is said “Tekanan darah anda hari ini seratus empat puluh empat atas lapan puluh tujuh.”
✓ the queue is staff's: Pa's own key is refused, NotStaff (403), and so is no key at all
✓ GET /review/status: the first 50 of each card type, 0 sources waiting; flagged until their first fifty are decided: flag, now, reading, visit, memo, reorder, notice, gate, story, learning
    reading    7 queued,  0 decided, flag True
    …
✓ Pa's reading card is sample 5 of its type, lines only — no profile id, no name, Mei is {name}:
    Your blood pressure today was 144 over 87.
    It is in your blood pressure book.
    {name} can see it too.
    filled from: backend/app/delivery/strings:HEADLINES.reading:en, backend/app/delivery/strings:LINES.reading.0:en, …
✓ a rewrite is a proposed catalogue change, checked by the plain-words verifier, and nothing more:
    backend/app/delivery/strings:LINES.reading.1:en
    from: It is in your blood pressure book.
    to:   Nura keeps it in your blood pressure book.
✓ Pa's card still says “It is in your blood pressure book.”; the rewrite waits in GET /review/proposals for a person to make it in the catalogue
✓ the pharmacist approves the now card (decided by pharmacist); deciding it again is refused, AlreadyReviewed (409)
✓ cp23-00869.example.sg is on the list as pending: a self-search naming it is refused, SourceNotAllowlisted (400) — nothing from it can reach Pa
✓ approved, it is allowlisted: the same self-search is accepted (201)
✓ the second source is rejected with a reason and stays off: allowlisted false, review_status rejected
checkpoint 23 passed: every step did what docs/checkpoints.md says
```

**What "passed" means.** Every line is a ✓ and the last line says `checkpoint 23 passed`. The criteria: `make language` finds 0 failures — every English line has its Malay and Chinese twin, twins fill the same slots, one English line is one line in each language wherever it is filed, the glossary's words (§6) are the ones used and the words it rules out are not; what it notes is only what cannot be edited in place (a consent's words, an approved WhatsApp template), each with its follow-up. Every card carries a voice script computed from its own verified lines — the numbers said as words in the card's language, the card's own connecting word ("over", "atas", "比"), a pause after each line and a longer one before the boundary — and no other words. The queue answers staff only: a patient's key is refused like no key. What it holds names no profile and no person: a name that filled a slot is `{name}`, the doctor `{doctor}`, and a line of his own record's words is not kept. A card type is flagged until its first fifty are queued and decided. A rewrite is a proposal with the catalogue id it would replace, and changes nothing he is shown. A new source is pending and unusable — a search naming it is refused — until it is approved; a rejected one stays off. If the first fifty readings are already queued on your `dev.db`, the checkpoint says so: `make reset-db` and run it again.

**Two things to try by hand** at http://127.0.0.1:8000/docs, after a run, with `Authorization: Bearer nura-dev-pharmacist-token-0001`:

1. **A rewrite the verifier refuses.** `POST /review/items/{item}/rewrite` on a pending reading sample with a body line "One reading was missed.": refused, `RewriteNotPlainWords`, with the verifier's finding (rule 11, a red word) — nothing is kept.
2. **The whole memory.** `cd backend && python3 -m app.language.memory --table` prints every patient line with its id (`catalogue:key:language`); `make language` prints the findings, and `--quiet-notes` leaves out the follow-ups.

## How to run checkpoint 25

The Record is the web client's (W5) over routes the backend already had — E03's timeline, episodes, providers and what changed, E04's medicines, draft and story, E09-01's trend, E10-01's routine, E02's review cards and the machine's screen — and two new ones for the reorder card (E04-05): `POST /profiles/{id}/medicines/{line}/ask-to-order` (his tap: a task on the family's list for whoever is on duty, else his chief, and a notice to his chief) and `POST /profiles/{id}/medicines/{line}/more` (tablets found at home, with a yes minted at `POST /profiles/{id}/confirmations`, subject `count_correction`). Nothing is mocked. The people come from checkpoints that already exist: each prints the numbers it signed up (`Pa (+6591117507) registered by phone code…`), and you sign in on the web with those numbers, the code being the newest one for that number in the `make dev` terminal.

```sh
make dev                # terminal 1: the API on http://127.0.0.1:8000, log to backend/.dev.log
make web                # terminal 2: the app on http://127.0.0.1:5173/app/ (proxies /api)
make checkpoint N=16    # terminal 3: Pa and Mei (his chief), Dr Tan, the chest infection — note both numbers
make checkpoint N=17    # Pa, born 1951, with two cholesterol results, and Mei, who set his day
make checkpoint N=9     # Pa, with a lab report Mei forwarded on WhatsApp waiting for his yes
printf '\x89PNG\r\n\x1a\nnura-paper-placeholder:bp-cuff-2026-09-14\n' > ~/Desktop/cuff.png
printf '%%PDF-1.4\nnura-paper-placeholder:a-letter-not-a-label\n' > ~/Desktop/not-a-label.pdf
                        # the blood pressure machine's screen the fixture reader knows, and a file that is not a label photo
```

**As Pa from checkpoint 16 (his own papers, *Big and simple*).** Sign in with his number and tap *Papers* in the nav.

1. **The first screen.** *Your papers*, and three plum buttons first — *Your medicines*, *Papers waiting for your yes*, *Your day* — then the rest, one big button each.
2. **Your medicines.** One medicine a screen: *Your blood pressure tablet*, *amlodipine 5 mg* small under it, how many are left, *You said yes to this.* and where it came from (*This comes from the label you kept on …*). *About this medicine* is the story: *What it is for*, *How to take it*, *What to look out for*, *What to stay away from*, *If you forget it*, then the boundary, last. *Hear* reads it on the phone; nothing plays by itself.
3. **Add a medicine.** *Add a medicine* → *Take a photo* (any photo on the Mac): Nura cannot read it, so type *warfarin*, *3 mg*, *1 tab OD*, *28*, *Dr Tan* → *Check it* → *This is a new medicine for your list.* → *Add it to my list* → *Nura added it to your list.* Add *aspirin*, *100 mg*, *1 tab OD*, *5* the same way: *Check it* shows *aspirin and warfarin*, *This one matters a lot.* and the question for Dr Tan, before anything is saved; then *Add it to my list*.
4. **The reorder card's buttons.** Five tablets is under the threshold, so the aspirin now has *Ask the family to order.* and *I have more at home.* The first: *Nura asked Mei to order more of the aspirin.* — a task on the family's list for Mei (she is his chief and nobody is on the roster; with a roster it goes to whoever is on duty, and Mei is told), and a notice to her. The second: type *20* → *Yes, add them* → *You have 25 tablets of the aspirin left.* The same two buttons are on the reorder card in the feed (*Today* → *See more for you*).
5. **Not from a label photo.** *Add a medicine* → *Choose a file instead* → `not-a-label.pdf` → type *warfarin*, *1 mg*, *1 tab OD* → *Check it* → *Add it to my list*: *Please take a photo of the label first.* — a high-risk medicine is saved only from its label photo, and nothing was written.
6. **Your visits.** The spine's three anchors in his words — *Your last check-up was with Dr Tan on …*, *Your last visit …*, *Your next visit is to Dr Tan on …* — then one visit or illness a screen, *This is 1 of 3.*, *Next*.
7. **The machine's screen.** *Today* → *Write it down* → *Take a photo of the machine* → `cuff.png`: *This is the screen of a machine.*, 138 and 84 already in their boxes → *Looks right*. The reading is written with no typing.

**As Mei from checkpoint 16 (his chief, *Smaller, with more on the page*).** Under *Me*, *Sign out*; sign in with Mei's number and open Pa's papers.

8. **What changed.** First on her Record: what is new since her last look (checkpoint 16 already looked twice), then *Still waiting*.
9. **An illness.** *Your visits* is one list; *See this illness* → *chest infection*: its papers, what was written down during it, the visits during it. Under *Put a paper with this illness*, the photo of the machine from step 7 → *Put this paper with it* → *Put this paper with this illness?* → *Yes, put it there* → *The paper is with the illness now.* The yes is hers, for exactly that paper and that illness.
10. **Dr Tan.** *Your doctors and clinics* → *Nura has 2 visits here.* → *See this doctor*: the visits, the paper, the medicine on his name, and *Notes about this place* with *parking at B2*. Type *bring the warfarin* → *Keep the note*: *Nura cannot keep a note that names a medicine or an illness.* Only Pa and his chief see these notes.

**As Pa from checkpoint 17.** *Your blood tests* → *Your cholesterol*: the backend's lines — the result, the range on his blood test, the direction since 2023 — then each result with its range (*The range is under 200 mg/dL.*) and whose range it is (*This range is printed on your blood test.* for Bukit Lab's, *This range is from a guide for your age.* for the other), and the boundary last. *Your day*: one line per moment, in his words. Choose *Bahasa Melayu* under *Me* to read both in Malay. **As Mei from checkpoint 17:** *Your day* is a table — each moment, its time, its medicines, what to check. *Set the day* → tap *Blood pressure* under *Lunch* → *Check the day* → *Is this the day?*, read back → *Yes, set the day* → *Nura wrote down the day.*

**As Pa from checkpoint 9.** *Papers waiting for your yes*: *This is a blood test.* — the lab report Mei forwarded on WhatsApp → *Look at this paper*: the review card, each line as read and how sure → *Looks right* → *Nura wrote it down.* and nothing waits.

**The family's papers** (E12-09) — the lasting power of attorney and what it backs — are on the *Family* screen, W6's (checkpoint 26); the Record does not repeat them.

**A closing account** (#151). Once Pa closes his account (*Family* → *What you said yes to* → *Nura keeps your papers*), every Record screen, his and his chief's, says *Nura has stopped keeping these papers.* and shows nothing of them; the backend refuses each read as `AccountClosing`.

**On your iPhone.** Same as checkpoint 10 (`http://<Mac's address>:5173/app/` in Safari, on the same Wi-Fi). *Take a photo* and *Take a photo of the machine* open the back camera. A real photo is not one of the fixture papers, so until the real readers exist (E02) Nura answers *Nura could not read this page.* — that is the fixture, not the screen; the Mac's `cuff.png` shows the full read.

What you will see (the operator's walk: `make build-web`, then `make web-e2e`, which starts `make dev` with the clock frozen):

```
✓ record-medicines.spec.ts › his medicines (patient|caregiver): each line with its source and how sure, Ask-to-order, I-have-more, the story
✓ record-medicines.spec.ts › the reorder card on his feed carries Ask-to-order and I-have-more (patient|caregiver)
✓ record-medicines.spec.ts › add a medicine (patient|caregiver): screened before it is saved, the severity and both medicines named; a high-risk one from a file is refused
✓ record-timeline.spec.ts  › his visits (patient|caregiver): the three anchors, a page and the next; an illness and a paper put with it on the chief's yes
✓ record-timeline.spec.ts  › his doctors (patient|caregiver): Dr Tan with his visits and the chief's note; a note naming a medicine is refused
✓ record-timeline.spec.ts  › what changed (patient|caregiver): read twice with a write between
✓ record-day.spec.ts       › his cholesterol over time (patient|caregiver): each result against its range, the direction in words, the boundary last
✓ record-day.spec.ts       › the day: the chief sets it once on her yes; it reads to him as one line per moment and to her as a table
✓ record-papers.spec.ts    › the Record's first screen: his medicines, his papers and his day first; a helper sees only what her key opens
✓ record-papers.spec.ts    › on a demo deployment the banner is on every Record screen, and still nothing is drawn over a line
✓ record-papers.spec.ts    › a closing account (patient|caregiver): every Record screen says the backend's AccountClosing sentence, and none of his papers
✓ record-papers.spec.ts    › a paper forwarded on WhatsApp is confirmed on the web (patient|caregiver)
✓ record-papers.spec.ts    › a blood pressure read off the machine's screen, confirmed with no typing (patient|caregiver)
23 passed
```

**What "passed" means.** In *Big and simple* every Record screen is one thing — one medicine, one visit, one paper — with *This is 1 of N.* and *Next*, 56px buttons, and nothing drawn over a line, the demo banner showing or not; in *Smaller, with more on the page* the same screens are lists and a table. Every line on a card is the backend's — the anchors, what changed, the story, the count, the trend, the day, who was asked to order — and the screens' own words are only titles and buttons; a refusal is one plain sentence (a note naming a medicine, a high-risk medicine without its label photo, an account being closed). A medicine is checked before it is saved, a count moves only on his yes for that number, a paper goes with an illness only on the chief's yes for exactly it, and the day is set only on hers. A helper's key sees only the parts it opens. Nothing of the Record is kept on the phone. If a step does not do that, tell the operator which one and what you saw instead.
## How to run checkpoint 26

Family on the web (W6): the web half of the family stories, walked by two people on two browsers. Three terminals at the top of the repo, the same as checkpoint 10; the household comes from checkpoint 13's script, so there is nothing to type into `/docs` to set it up.

```sh
make build-web          # once: the app the backend serves at http://127.0.0.1:8000/app/
make dev                # terminal 1: the API and the built app, log to backend/.dev.log
make checkpoint N=13    # terminal 2: Mei, Pa (in Malay), Siti and Kit, with their keys, the roster and a task
```

Checkpoint 13's output names four fresh phone numbers — Mei's first, then Pa's, Siti's and Kit's (for example `Mei (+6594447692)` and `Pa (+6593332250)`). Keep that terminal open: those are the numbers you sign in with. Every login code prints in the `make dev` terminal (or `backend/.dev.log`), as in checkpoint 10; nothing is sent anywhere.

**Two browsers.** Pa is on your iPhone: Safari at `http://<your Mac's address>:8000/app/` on the same Wi-Fi (`ipconfig getifaddr en0` gives the address; checkpoint 10 says why Safari will not install it as an app over plain http). Mei is on the Mac: Chrome or Safari at http://127.0.0.1:8000/app/, with the window made 360 wide (Safari: *Develop → Enter Responsive Design Mode*, 360 × 640; Chrome: DevTools' device toolbar). If you have no iPhone to hand, open Pa in a private window on the Mac instead: the two sessions never share anything.

**Pa, on the iPhone (the big and simple look).** Sign in with Pa's number and the code. Pa's papers are in Malay (checkpoint 13 set him up that way); tap *Saya* → *English* if you would rather read English — every line on Family is then asked of the backend in English. Tap **Family** in the tab bar (Today · Family · Me).

1. *Who can see your papers*: Mei's, Kit's and Siti's keys, each in whole sentences from the backend — who they are to him, the parts they see, for how long. Nothing is drawn over a line; every button is 56 points.
2. *Who looked at your papers*: his trail by day, newest first, every sentence his, a refused reach included ("Mei asked to see your private notes on …"). No class name, no table, no id.
3. *Keep a part to yourself*: checkpoint 13 already marked his private notes; they show *Only you*. Tap *Private notes* → *Let them see it again*, then mark them again with *Yes, only me*. Each is one screen, one yes. Mei's next read of the notes is refused at once, and it is on his trail.
4. *What you said yes to*: every agreement in force, in the words he read. On Kit's, tap *Stop this*: the backend says what that will do ("If you stop this, Kit cannot see your papers." …); *Yes, stop it*. "Kit cannot see your papers now." Kit's key is closed in the same transaction, and nothing waiting to be sent reaches him. WhatsApp has *Stop this* too (#143): it says exactly what changes — Nura stops messaging him there, he leaves the family's group, and who is still told when he is unwell, by name — because his family's red-flag notices rest on their own keys. Keeping his papers has *Close my account*: it shows what closing means and the day his papers go (`docs/trust/account-closure.md`); *Cancel* here, and nothing is closed. Stopping someone who holds his emergency card also says "Nura will not tell Mei when you are not well." *Keep a copy to print* shows the record — every agreement, the one just stopped included, with who stopped it and when — and *Save the page* keeps it as one page to print, with nothing fetched.
5. *Family messages*: today's digest, in whole sentences, with the family's own words under their names. Write "I slept well." and *Send to the family*.
6. *Visits from a calendar* (step 13 below puts two there): one proposal at a time; *Yes, book this visit* books it, *Not this one* books nothing.

**Mei, on the Mac at 360 wide (the smaller look).** Sign in with Mei's number, tap Pa's papers on the doors, then **Family**. The page never scrolls sideways.

7. *Change who can see what*: every key as its sentences. Under *Give someone a key*, type Siti's name and number, tap *Helper* (the backend's words for a helper appear, said for Siti), keep the parts, choose *30 days*, *Make the key*. On Siti's key, *Make it smaller*, untap *Emergency card* and *Messages Nura sends*, *Yes, make it smaller*: her sentences now name the medicines only. *Make it smaller* again, tap *Blood pressure book and sugar numbers* — wider — and *Yes, make it smaller*: "Nura cannot make this wider. The owner must agree to more first." Wider is a new agreement from Pa, never a change in place. *Close this key* → *Yes, close it now*.
8. *Who is on duty, and tasks*: the roster as a table (checkpoint 13's Mei on weekdays, Kit at the weekend, 7 to 10 on his clock) and *On duty now*. Add a task "Buy the water pill" for Siti; tap *It is done* as Mei: "Only the person it is for can say it is done." (Siti's own tap, from checkpoint 13's script or `/docs`, is the one that counts.) *See the next visit and who drives* opens the Visit screen, where the roster's driver waits for Mei's yes (#128).
9. *Family messages*: write "Pa slept well. I will come by at 6." and send. Sign in as Kit in another private window: his digest has Mei's line and her words, and who is on duty.
10. *Messages for Pa*: *A pick-up time*, *When* "pukul 9", *Bahasa Melayu*, *See it as it will look*: "Mei akan ambil anda pada pukul 9." / "Bawa buku tekanan darah anda." — exactly what he will see. Set *Send from* two minutes ahead and *Schedule it*: *Waiting to send*. When the two minutes are up, at http://127.0.0.1:8000/docs call `POST /dev/run-triggers` with `{"profile_id": "<Pa's profile id from checkpoint 13>"}` (or wait for the next run on a deployment): the message says *Sent*, with the minute it went. It reaches him on WhatsApp once he has agreed to WhatsApp (step 12).
11. *The week in numbers*: taps, *Fine today* and its share, each kind of nudge given, taken up and put aside — counts only, never his words; her read is on his trail. *What Nura sent*: every attempt to reach someone about him, to whom, when, by which channel, what became of it, and the rule that fired. *When and how Nura sends*: change *Quiet from* and *Keep these settings*; a red flag says *Never held*. *Papers for the family list*: *Lasting power of attorney*, choose a PDF: it is listed with what it backs.
12. **I'm on it.** At `/docs`, as Pa (his token from checkpoint 13's log, or sign in by phone there), agree to WhatsApp (`POST /profiles/{id}/consents/whatsapp` with `{"wording_version": "1", "language": "ms", "captured_via": "app"}`) and press not feeling well (`POST /profiles/{id}/not-feeling-well` with `{"words": "chest pain"}`) while Mei is on duty. Mei's Family opens on "Nura asked you to check on Pa on …" and *I'm on it*: "Nura asks nobody else now." — the ladder stops for everyone after her, as Siti's WhatsApp reply does in checkpoint 20.
13. **The calendar.** On Pa's phone (or as Pa on the Mac), *Visits from a calendar* → *Choose a calendar file* → `backend/tests/fixtures/calendar/three-events.ics` (AirDrop it to the iPhone, or pick it on the Mac). Pa reads the calendar words and *I agree*; two visits are proposed, the lunch is kept nowhere. On Mei's, the same file after that makes the same two proposals, and *Not this one* puts one aside; Pa's *Yes, book this visit* books the other.
14. **The owner's alone.** As Mei, *What Pa said yes to* → *Stop this* on any agreement: "Only the owner can stop this." *Keep a part to yourself* → a part → *Yes, only me*: the backend's no, in its words. Nothing is ever a greyed-out button with no words.

**The pharmacist's queue.** On the Mac, open http://127.0.0.1:8000/app/review/ — a page of its own, never linked from the patient app and never kept by its service worker. Pa's session token (from `backend/.dev.log` or the doors) typed as the staff token is refused: "Only Nura's pharmacist can open this." The laptop's staff token, `nura-dev-pharmacist-token-0001` (the Makefile's, refused anywhere but a dev run), opens it: the first 50 of each card type with *Still to check* until each is decided, and the cards waiting, with nobody in them (`{name}`, no profile). Approve one, reject one with a reason, rewrite one as a proposal. On a demo deployment the demo banner is first here too.

What you will see (the operator's walk, `make web-e2e` with `make dev` serving the build):

```
✓ family.spec.ts › the nav: Today, Family, Me
✓ family.spec.ts › Pa's Family, one thing a screen: his circle, his trail, a part kept to himself, and Mei refused on his trail
✓ family.spec.ts › Pa stops letting Kit in after reading what it will do, Kit is out at once, and the record is his to print
✓ family.spec.ts › Pa's calendar one proposal at a time: his yes books the visit, a no books nothing; the family's messages
✓ family.spec.ts › the caregiver density at 360 by 640 › Mei's keys: a helper's key by role, parts and window; made smaller; wider refused in the backend's words; closed
✓ family.spec.ts › the caregiver density at 360 by 640 › Mei's roster and tasks: Mei weekdays, Kit weekends; a task only Siti can mark done; the visit one tap away
✓ family.spec.ts › the caregiver density at 360 by 640 › the family thread: Mei writes on her phone, Kit reads the digest on his
✓ family.spec.ts › the caregiver density at 360 by 640 › a message to Pa, previewed in Malay, scheduled, then sent by the delivery engine; the delivery log says what went
✓ family.spec.ts › the caregiver density at 360 by 640 › the week in numbers, when and how Nura sends, the papers behind the family list; what is the owner's alone is refused in the backend's words
✓ family.spec.ts › the caregiver density at 360 by 640 › a calendar file on Mei's phone: two proposals, the lunch kept nowhere, one put aside
✓ family.spec.ts › the caregiver density at 360 by 640 › a red flag reached Mei: she says she is on it, and the ladder asks nobody else
✓ family.spec.ts › the for-someone door: who you are to them is a choice, and the number can come from the phone's contacts
✓ review.spec.ts › the pharmacist's queue: a patient's token refused, the staff token opens it, approve, reject with a reason, rewrite as a proposal; nobody in it
```

**The for-someone door (E01-01).** Sign out, sign in with a fresh number, *This is for someone else*: who you are to them is a set of choices (*Their daughter*, *Their son*, *Their husband or wife*, … *Someone else*), never typed: a code goes to the backend, which says it to him in his own language ("Mei, your daughter, made this for you." / "Mei, anak perempuan anda, …" / "Mei（您的女儿）…"). Letting someone in from *Set up Nura* takes the same choices. On a phone whose browser has the Contact Picker (Chrome on Android), *Choose from my contacts* fills the number and the name from one contact; Safari on iOS has no picker, so the number is typed there (ADR 0001's table).

**What "passed" means.** Pa did each thing on one screen at a time, with 56-point buttons and nothing over a line, and every sentence about his papers was the backend's, in his language; Mei did hers at 360 wide with nothing sideways; each refusal was said in the backend's words where it happened, never as a greyed-out button; Kit was out the moment Pa stopped letting him in, and the record says so; the message said *Sent* only when the delivery log did; and the staff page opened only for a staff token. If a step does not do that, tell the operator which one and what you saw instead.

## How to run checkpoint 27

Checkpoint 27 is the patient's day in the web client (W7): the not-feeling-well button, the feeling cloud, the symptom log, the day's nudge, today's top three, the whole pre-visit brief, the questions, the post-visit card's yes, the clips on his feed, the number on Me, and the wash. Every line he reads is the backend's, in the backend's order; the screens only lay them out. The operator's walk is `make web-e2e` (`web/tests/e2e/day.spec.ts`); this is the same walk by hand.

**Set up, on the Mac.** Two terminals at the top of the repo, as for checkpoint 10. Start the backend with the clock stood at ten in the morning on Monday 14 September, so what you see matches the lines below (leave `NURA_FROZEN_CLOCK` out to use today instead):

```sh
make build-web                                              # once: the app, served by the backend
NURA_FROZEN_CLOCK=2026-09-14T10:00:00+08:00 make dev        # terminal 1: http://127.0.0.1:8000/app/
make web                                                    # terminal 2, optional: http://127.0.0.1:5173/app/ (and the phone)
```

1. **Pa.** Open http://127.0.0.1:8000/app/, sign in with a fresh `+65` number and the name *Pa* (the six digits are in the `make dev` terminal), tap *This is for me*, *I agree*, then *Set up later*. You are on Today, and under the greeting is **I am not feeling well**.
2. **Mei, his chief.** In a second browser window (a private one), sign in with another fresh number and the name *Mei*. Back in Pa's window, at http://127.0.0.1:8000/docs with Pa's token (*Authorize*): `POST /profiles/{id}/consents/sharing` with Mei's number, `"holder_display_name": "Mei"`, every part in `scopes`, `"relationship": "daughter"`, `"language": "en"`, `"captured_via": "app"`; then `POST /profiles/{id}/keys` with `{"holder_phone_e164": "<Mei's number>", "role": "chief"}`.
3. **His blood pressure tablet and Dr Tan.** Still at `/docs` as Pa: add the tablet the way checkpoint 10 does (`/photos`, then `/confirmations` with `"subject": "medicine"` and the amlodipine label, then `/medicines`), and put Dr Tan in his directory with a visit on his yes: `POST /profiles/{id}/providers` `{"name": "Dr Tan", "kind": "doctor"}`, `POST /profiles/{id}/confirmations` `{"subject": "appointment", "provider_id": …, "scheduled_at": "2026-09-14T10:30:00+08:00", "purpose": "blood pressure check"}`, `POST /profiles/{id}/appointments` with the same and the `confirmation_id`.

**On the Mac, what you will see.** Reload Pa's Today after each step.

- **The feeling cloud** (E17-01): the new tablet changed State, so under *Now* is "Your blood pressure tablet is new since Monday 14 September." and "How are you feeling today?", then the words, biggest first — *Dizzy* and *Swollen ankles* first, *Fine today* last. Tap **Dizzy**: one question, "When did it begin?", and its four answers — *Today*, *Since yesterday*, *A few days*, *A week or more*. Tap *Since yesterday*: the note kept for the visit — "Things to tell Dr Tan", what to tell him, who does the next thing, and the boundary last. *Back to Today*: the strip is gone, and stays gone until State changes again.
- **I am not feeling well** (E13-02): type "tired today" and tap *Tell Nura*. The card is the backend's, all of it, in its order: "Mei knows now.", then what to do now (with the tablet not tapped *Taken* today, "Nura has no note that you took your blood pressure tablet today." and "Ask Dr Tan before you take your blood pressure tablet."; once it is tapped, "Sit down and rest now."), "Mei will call you today.", "Nura will ask you again in 2 hours.", and the boundary. Mei is told: the backend writes her notice, and `GET /profiles/{id}/deliveries` lists the attempt to reach her once delivery has run (`POST /dev/run-triggers` `{"profile_id": …}` on a dev run).
- **A red word** (E13-02, E17-02): press the button again and tap *Say it out loud*, say anything, and *Stop and send* (on a dev run the fixture transcriber hears only its placeholder notes, so to hear "chest pain" type it instead). The card: "Mei knows now." / "Call the ambulance now on 995." / "After that, call Mei." / "Nura does not decide what is wrong." — nothing after the ambulance but the one closing line. *Back to Today*: State is *act* and the wash fades from lavender to coral over about a second. With *System Settings → Accessibility → Display → Reduce motion* on, the coral is simply there.
- **The flag first.** With a fresh Pa (steps 1–3 again), tap **Chest pain** on the cloud: the same urgent card. In the browser's developer tools (*Network*), the `POST …/feelings` is the first request after the tap and nothing else finishes before it. Then `POST /dev/run-triggers` `{"profile_id": …}` and `GET /profiles/{id}/deliveries`: a delivery of type `flag` on the ladder the tap started.
- **No network** (ADR 0012): with Today open once online, turn the network off (Safari *Develop → Network Conditions → Offline*, or Wi-Fi off) and press *I am not feeling well*, type anything, *Tell Nura*: "You did right to say so." / "Nura could not send this to your family." / "Call Mei now." / "If you feel very bad, call the ambulance now on 995." / "Nura does not decide what is wrong.", under "Nura cannot reach the internet right now." A red word on the cloud with no network gives the red card instead: "… Call the ambulance now on 995." / "After that, call Mei." Never nothing, and never "Mei knows now." when nobody was told.
- **How you feel** (E14-01): *Write down how you feel*, type "dizzy, quite a lot, since this morning", *Keep this*: "Nura wrote this down." and "Pa felt dizzy on Monday 14 September." / "It was quite bad." / "It started this morning." / "Pa wrote this down.", and the week's log under it. In Mei's window: *Pa's papers* on the doors, then *Write down how you feel*: "How Pa has felt", the same lines.
- **The day's nudge** (E11-07): on a fresh Pa with no tablet (steps 1 only), Today has the day's nudge from 10:00 on his wall — "Nura is here if you need it.", its why under it, "You see this because it has been a quiet week.", then *OK* and *Not today*. *OK*: it is gone, and `GET /profiles/{id}/nudges` shows it answered. While the feeling cloud is on Today, a check-in nudge is not shown: the cloud is the check-in.
- **Today's top three** (E11-02): *For you today* is the backend's first card with its why and *Next*; *Next* shows the second, then the third; the last has no *Next*.
- **The visit** (E05-01, E05-02): *See your next visit*, then **Read before your visit**: the whole brief — who and when, what it is about, what changed, what to bring — and its boundary last. **Your questions for the doctor**: type "Is the water pill bad for my kidneys?", *Keep this question*, "Is this what you want to ask?", *Yes, keep it*: it is on the card. *Take this question off*, *Yes, take it off*: it is gone. "only the part for you" is refused: "Please write the question in plain words."
- **The post-visit card** (E05-05): record the visit as checkpoint 22 does (or, at `/docs`, `POST …/appointments/{appt}/transcript` with a transcript from `backend/tests/fixtures/visits/`). Open the Visit screen: "This card is waiting for your yes.", each line with *Hear what Dr Tan said* under it when the recording has it (or "This comes from the notes you wrote."), and *Leave this out* under each thing heard. "Ask Dr Tan about the new amount of the water pill (frusemide)." is a question for Dr Tan, never an amount. Leave one out, tap **Yes, keep this card**: "Nura kept what Dr Tan said." and the memo card, without the line you left out.
- **Clips on the feed** (E21-03): *See more for you*, page to the memo card: *Hear what Dr Tan said* under a line plays only that stretch, its words shown under the button while it plays. A key that may not hear the recording (a viewer's, a clinic's) sees "Only the owner and the family he let in can hear this." in place of the button.
- **Me** (E17-04): the number that only goes up, in the backend's words: "Nura counts the days with your tablets taken." / "This number only goes up."

**On your iPhone.** On the same Wi-Fi, `make web` answers on the Mac's address (`ipconfig getifaddr en0`): open `http://<that address>:5173/app/` in Safari and walk the same steps, signing in with the numbers above. Over plain http on a Wi-Fi address Safari gives a page no microphone, so *Say it out loud* is not offered there — type instead; on the Mac (`127.0.0.1`) and on the https demo (checkpoint 19) it is. On the demo the banner "Demo — not for real health information" stays at the top of every screen, and the what-to-do card is always under it, never beneath it.

What you will see (the operator's walk, `make web-e2e` with `make dev` serving the build):

```
✓ day.spec.ts › not feeling well, typed: the backend's card, every line in its order — Mei told, a check-in in two hours
✓ day.spec.ts › a red word said out loud: the flag first, the urgent card as sent, and the wash cross-fades to act
✓ day.spec.ts › a red word on the cloud reaches the flag before any other request, the ladder is written, and the strip goes
✓ day.spec.ts › a word, its one question, and the note kept for the visit — the strip goes after the tap
✓ day.spec.ts › no network on a red word: the backend's offline card the phone kept — and with none kept, the same words built in; never nothing
✓ day.spec.ts › a symptom said out loud, with how much and since when; Mei reads it in plain words on her phone
✓ day.spec.ts › the visit: the whole brief in its order, and his questions added and taken off on his yes
✓ day.spec.ts › the post-visit card on the web: each line with where it was said, one left out, his yes, the memo card; the dose change stays a question; the memo card's clips
✓ day.spec.ts › the day's nudge where the backend plans it, with its why: OK, and it is gone; the proud number on Me in his words
✓ day.spec.ts › today's top three: one card a screen with Next, in the backend's order, each under its why
✓ day.spec.ts › the wash cross-fades when State changes, and with Reduce Motion the new wash is simply there
```

**What "passed" means.** Every line on these screens is one the backend sent, in its order, none dropped — the what-to-do card above all, which starts with who knows and ends on its boundary; a red word, whether tapped or said, is sent before anything else and takes the red-flag path, and the ladder it starts is the one delivery climbs; with no network the phone shows the backend's offline card and never says the family knows; nothing plays until you tap it; every button is 56 by 56 and nothing is drawn over a line, with the demo banner shown too; and the wash fades on a change of State unless Reduce Motion is on. If a step does not do that, tell the operator which one and what you saw instead.

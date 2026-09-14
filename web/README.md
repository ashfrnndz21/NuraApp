# Nura — the web client

The app the patient opens in Safari and adds to the home screen (ADR 0001). TypeScript in
strict mode, Preact with signals, Vite, CSS custom properties, Vitest for units, Playwright
for the phone-sized end-to-end flow. No UI framework beyond Preact, no CSS framework.

```sh
make web         # dev server on http://127.0.0.1:5173/app/ (proxies /api to make dev); --host for the phone
make build-web   # web/dist, which make dev then serves at http://127.0.0.1:8000/app/
make web-test    # Vitest: strings, refusal map, Today model, the kept page, the voice, contrast
make web-e2e     # Playwright against the built app the backend serves (needs make dev)
make web-mock    # make web, with E01's onboarding routes answered by src/api/mock/ until E01 merges
npm run plain-words   # the backend's verifier over web/src/strings/*.ts only
```

## Layout

- `src/ui/tokens.css` — docs/design-system.md §2 as custom properties; the two densities are
  `data-density="patient|caregiver"` on `<html>`, the wash is `data-posture`.
- `src/strings/{en,ms,zh}.ts` — every patient-facing line, each under a `// @patient [kind]`
  tag the backend's verifier reads (`app.safety.plain_words.strings_in_typescript`).
  `refusals` maps every refusal class name to one plain sentence.
- `src/api/` — `client.ts` (bearer header, `/api` base, the `{"refusal": …}` shape as a
  `Refused` error, one call at a time), `nura.ts` (one function per route), `types.ts`.
- `src/store/` — `kv.ts` (IndexedDB), `session.ts` (token, profile, language, density).
- `src/flow.ts` — which screen is up and the doors logic. `src/screens/` — one file per step.
- `src/today/` — the Today model: the Now card from the backend's `due_now`/`missed`, the feed's
  cards for today, the State card with the backend's boundary, the medicines card with the
  questions for the doctor, the day and time in his words.
- `src/onboarding/` — onboarding's logic apart from any screen, all unit-tested: `cloud.ts`
  (which words show, how big, in what order), `about.ts` (the questions and what the answers
  change on the phone), `review.ts` (one decision per review-card field), `plan.ts` (which gap
  cards show), `dates.ts`; `state.ts` is where the session is, in memory only.
- `src/screens/onboarding/` — one file per step: About, Cloud, Asks, ReadBack, Records (the
  prompt, the capture and the review card), Questions, Plan.
- `src/api/mock/` — dev only: the stand-in for E01's routes under `VITE_API_MOCK=1`.
- `src/speech/speak.ts` — `speak(card)`: the one seam for the spoken twin.
- `src/sw/sw.ts` — the service worker; `src/offline/` — its registration and the Today cache.

## Design decisions

**Token storage.** The bearer token lives in memory and in IndexedDB, never in a cookie.
The API authenticates by the `Authorization` header alone, so a cookie would add nothing
but a value the browser attaches to every request to the origin — `/docs`, static files,
anything — and a cross-site request surface to defend. IndexedDB is per origin, survives
the home-screen app being closed, and is not sent anywhere. Sign-out deletes the token, the
chosen profile and every cached Today page; switching profile deletes the previous
profile's page. The device's language and look are the only things that stay.

**What the phone keeps of his papers.** One Today page per profile (`today.<profile_id>`
in IndexedDB): the State (id, posture, staleness, boundary), today's dose cards, the
reconciled list with its counts and questions, the feed's first page, and the proud number
— bound to the key that read it (or "owner") and to that key's scope set, and good until
the local midnight after it was read. Every refresh first re-reads the profile: a different
or narrower key deletes the entry before anything else is read; any refused read deletes it
and the refusal is shown; an entry past its midnight is deleted, not shown, and with no
network the page is only the emergency-card placeholder and "Nura cannot reach your papers
right now." — no dose from old data. A kept page is shown as today's list with the time it
was read, never as a Now card with Taken. Nothing else about the record is stored on the
device.

**API serving: one origin.** The backend serves every route both at the root and under
`/api` (one router included twice), and serves `web/dist` at `/app` when
`NURA_WEB_DIST` names it. The client only ever calls `/api/...` on its own origin: no CORS,
no cookies, and the service worker can tell the shell (cached) from health data (never
cached, by path). In dev Vite serves the source at `:5173/app/` and proxies `/api` to
`:8000` by one rule; the built app is what the phone will get from the deployment.

**Requests one at a time.** `api()` queues calls. A person does one thing at a time, and the
local SQLite database refuses two requests that each read and then write their audit line
concurrently; the queue costs milliseconds and makes the laptop behave like the deployment.

**Speech.** `speak(card)` reads the card's lines with the Web Speech API using only a
voice that runs on the phone (`localService`), in en-SG, ms-MY or zh-CN; with no local
voice for the language it stays silent rather than send medicine names to a vendor's
servers outside the region. It is called from the Hear button and from nowhere else —
never on load, never when the next card appears. The backend's pre-rendered voice is a
later adapter set with `setSpeaker`; nothing else changes.

**No dose is composed here.** The backend marks every dose `due_now` or `missed` by an anchor
window of his day (`app/medicines/windows.py`; on each slot of `GET /medicines/today` and each
line of `GET /medicines`). The Now card is the first slot the backend marks due; a dose whose
window has passed shows the story's own missed-dose lines (E04-07) and no Taken; the questions
for the doctor (dose changes, interaction flags) are the backend's lines on the medicines
card. Every card fills its source line with the backend's: `source` on a medicine line or a
slot, `why.plain` on a feed card. The State card carries the State's id and staleness and the
State's own `boundary` lines; a stale State says only that it is from earlier today and shows
no dose card; an `act` posture comes first and says what to do — the flag card above it, or
"Call {chief} now." — never a calm sentence.

**For you today.** The feed's first two `now`/`today` cards (`GET /profiles/{id}/feed`), in
the backend's order, each under its `why` and, on an inferring card, its own `boundary`; a
red flag card goes first on the page. When the feed has nothing for today (the quiet hours
21:00–07:00, or nothing new), the State card and the medicines card stand in. The questions
for the doctor are shown either way.

**Consent words from the API.** `GET /consent/wording` hands the client today's words and
their version, so the yes on the for-me door is for exactly what was shown and no client
carries a copy of the wording that could drift.

**Densities.** The owner of the papers gets the patient density (20px body, 56px targets,
paper under every card); anyone holding a key gets the caregiver density (16px, glass
first). The person can override it under Me; the choice is per device.

**The proud number.** `GET /profiles/{id}/proud`: distinct local days with a DOSE_TAKEN event
on the profile — the days he took his tablets, whoever tapped Taken — counted by the backend
from the memory events in one audited read. The client shows that number and never one it
worked out or kept for itself; the Today screen does not read the audit trail at all.

**A key without the records scope.** The State reads under `records`; a key without it (a
helper's, for the medicines) never asks for it, and its Today is the medicines and the feed's
caregiver cards, with no State card and no refusal.

**Reopening.** The app opens on the remembered Today at once and checks who is signed in in
the background; only a refused session sends him back to sign-in (`src/restore.ts`). A lost
network or a server error keeps him where he was. The kept page expires at midnight on the
profile's region clock (Singapore, Kuala Lumpur), whatever zone the phone is set to.

**Offline.** The worker precaches the shell on install (the Vite plugin in `vite.config.ts`
lists the built files into it) and answers navigations from the cache when the network is
gone. It never caches `/api`. The app keeps the last Today page per profile in IndexedDB and
renders it first (as today's list, dated), then the fresh one if it can — there is no
spinner either way.

**Dev vs build.** The worker is only registered from the build (Vite does not build it in
dev), so `make web` is for working on screens and the offline behaviour is proven against
`make dev` serving `web/dist`. Over plain http on a LAN address the browser will not
install a worker or offer "add to home screen" — that needs https, which the cloud
deployment brings; on the Mac, `127.0.0.1` counts as secure.

## Onboarding (W3)

About you → the word cloud → the follow-ups → the read-back → the papers (prompt, photo,
review card, one yes) → the questions the papers raised → the gaps → Today. It starts after
*I agree* on the for-me door and after *Set it up* on the for-someone door; *Set up later*
skips it and *Set up Nura* under Me starts it again.

**Live and mocked.** E01's backend (branch `E01-biography-profile`) is being built beside this
client. Until it merges, `make web-mock` (`VITE_API_MOCK=1`) answers its routes from
`src/api/mock/`, and `src/api/nura.ts` calls the real paths with the same shapes
(`src/api/types.ts`), so switching over changes nothing but the flag. The mock is in memory
for the tab, and a build without the flag has none of it (Vite drops the import).

| Route | State |
|---|---|
| `POST /profiles/{id}/photos`, `POST /profiles/{id}/confirmations` (`review_card`), `POST /profiles/{id}/review-cards/{card}/confirm`, `GET /profiles/{id}/review-cards/{card}` | live (E02) |
| `GET /onboarding/conditions?language=` | mocked until E01 |
| `GET` / `PUT /profiles/{id}/settings` | mocked until E01 |
| `POST /profiles/{id}/biography`, `/biography/read-back`, `/biography/papers`, `/biography/close` | mocked until E01 |
| `GET /profiles/{id}/plan?language=` | mocked until E01 |
| `POST /profiles/{id}/biography/questions` (Keep / Not this one), `POST /profiles/{id}/plan/later` | mocked; **assumed** paths, not in E01's announced list |

**Nothing kept on the phone.** Settings, words, the biography, review cards and the plan live
in memory (`src/onboarding/state.ts`) and on the backend, never in IndexedDB or web storage:
none of it could be bound to a key and an expiry, so none of it is cached. A unit test fails
if any onboarding file mentions browser storage; the e2e reads IndexedDB after the walk.

**No sentence is composed here.** Read-back lines, prompts, what a paper taught, questions and
gap cards are the backend's whole lines, shown with their `source` and their `state_id`
(`data-state-id`). The client's own lines are in the catalogue; slots take only a name, a
date or a number. A review-card correction is exactly what he typed (a number stays a number);
a structured value such as a dose instruction cannot be retyped, only kept or left out.

**One thing per screen, or the list.** In the patient density each About question, follow-up,
read-back line and question is its own screen, and the Ready screen shows one gap card and how
many follow. The caregiver density (a chief setting up for someone) gets each step as one page
and the full gap list (docs/gaps-and-unlocks.md §3). His answers change his own phone at once
(his language; the big look for small print, small buttons or memory) and never the chief's.

**The word cloud.** Plain words from the backend's graph, sized by how common each is (1–3)
plus one for every picked word that relates to it; top words heaviest first so they are on the
first screen; revealed words go straight after the word that revealed them, so nothing moves
under his finger; unpicking drops what only it revealed. A tap speaks the word and "Doctors
call it …" — the term is a slot value, shown only in brackets after his word.

# Nura — the web client

The app the patient opens in Safari and adds to the home screen (ADR 0001). TypeScript in
strict mode, Preact with signals, Vite, CSS custom properties, Vitest for units, Playwright
for the phone-sized end-to-end flow. No UI framework beyond Preact, no CSS framework.

```sh
make web         # dev server on http://127.0.0.1:5173/app/ (proxies /api to make dev); --host for the phone
make build-web   # web/dist, which make dev then serves at http://127.0.0.1:8000/app/
make web-test    # Vitest: strings, refusal map, Today model, the feed's store/cards/playback, the kept pages, the voice, contrast
make web-e2e     # Playwright against the built app; starts make dev itself, its clock frozen at 10:00 Singapore
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
- `src/feed/` — the vertical feed (W2, E21): `store.ts` (pages by cursor, prefetch, the kept
  first page, the side actions), `model.ts` (a card as the pager shows it, from the backend's
  item alone), `playback.ts` (Hear on tap: the backend's voice or the spoken twin), `session.ts`
  (one store per profile and key). The screen is `src/screens/Feed.tsx`; Ask is
  `src/screens/Ask.tsx`, a placeholder until E03's `POST /ask`.
- `src/speech/speak.ts` — `speak(card)`: the one seam for the spoken twin.
- `src/sw/sw.ts` — the service worker; `src/offline/` — its registration, the Today cache and
  the feed's kept first page (`feedCache.ts`).

## Design decisions

**The feed (W2).** Today's *See more for you* opens the vertical feed: a CSS scroll-snap
pager (`scroll-snap-type: y mandatory`, `scroll-snap-stop: always`) that is a size container,
so each card is the pager's height whatever the phone; up and down only (`touch-action:
pan-y`, `overscroll-behavior: contain`, no gesture handlers, no pull-to-refresh, no swipe to
dismiss). The pager is an ARIA `feed` of `article`s, each labelled with its spoken script;
Page Down / Page Up (and the arrows, Home, End on a focused card) move a whole card; it
scrolls smoothly unless Reduce Motion is on, and then moves at once. The store asks for the
next page by the cursor the last page handed back as soon as he is within two cards of the
end, asks for each cursor once, and never reorders what the backend sent: a red flag first,
now, today, the gate, his story, learning — and past the gate the backend cycles the story
and learning cards, so the list pages on. The same item can come round again, so a card is
keyed by its place, not its id. A fresh first page replaces what is on screen only while he
is still on the first card; once he is reading on, nothing moves under his finger.

**A card is the backend's.** Headline, body, the boundary an inferring card ends on (shown
apart, last), the why line, the spoken twin, the State id (`data-state-id`); the catalogue
only names the section and the buttons. A type the client does not know is shown as its own
lines. Every card has four visible buttons — *Hear*, *Ask*, *Family*, *Not for me* — 56px and
more, pinned to the bottom of the screen on a card taller than it; the gate keeps *Hear* and
its one action, *Keep going*. The now card's one action goes to Today, where *Taken* is and
where the backend says which dose is due. *Not for me* posts `dismissed` (E21's engagement
kind; for the owner the backend then holds that kind of card for the day). *Family* posts a
card reference to the family thread (E12) for the kinds the thread can carry — a reading, a
visit — and otherwise says it cannot send the card yet; no card's words are ever posted as a
message. *Ask* opens a placeholder until E03's `POST /ask` is on main. Heard, tapped and
shared are written back only by a key that may write events; *Not for me* is always sent,
and every refusal is said on the screen, never swallowed.

**Voice on tap only.** `feed/playback.ts` is one seam: it warms (fetches, never plays) the
backend's pre-rendered voice for the card on screen and the two after it
(`GET …/feed/{item}/voice`, E11), and *Hear* plays it inside the tap; when the route is not
there (a plain 404 — it stops asking) or has no voice for the card, it reads the card's
spoken twin through `speak()`, which uses only a voice on the phone. Nothing plays when a
card arrives or when a voice ends, and a card's voice stops when the card leaves the screen.

**The feed's kept page.** The first page (`GET …/feed/cached` answers the same page) is kept
as `feed.<profile_id>` under the Today page's rules: bound to the key and scope set that read
it, good until the region's midnight, deleted on a refusal, a switch of papers or sign-out,
and swept on every launch once past its midnight. With nothing kept, the pager opens on the
backend's cached page (cards past their own expiry left out) and then on the fresh one;
offline it opens on the kept page with the time it was read, and with nothing kept only the
emergency-card rule applies. `NoCachedPage` means nothing was ever rendered for him, and is
treated as nothing to show before the fresh page — not as a refusal of access.

**The caregiver's feed.** The same pager in the caregiver density: the backend's caregiver
supply (no gate; the duty card), and under each card what became of it on his page — kept
back, on his page, opened, or *Not for me* — from the backend's `status`.

**Token storage.** The bearer token lives in memory and in IndexedDB, never in a cookie.
The API authenticates by the `Authorization` header alone, so a cookie would add nothing
but a value the browser attaches to every request to the origin — `/docs`, static files,
anything — and a cross-site request surface to defend. IndexedDB is per origin, survives
the home-screen app being closed, and is not sent anywhere. Sign-out deletes the token, the
chosen profile and every cached Today page; switching profile deletes the previous
profile's page. The device's language and look are the only things that stay.

**What the phone keeps of his papers.** One Today page and one feed page per profile (`feed.<profile_id>`, above), and the Today page (`today.<profile_id>`
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
network or a server error keeps him where he was, and on Today a server that could not answer
(a 5xx) leaves the kept page in place, dated, under "Nura cannot reach your papers right now."
(`readFailure` in `src/restore.ts`); only a refusal deletes it. No page — kept or fresh — is
shown past the midnight after it was read on the profile's region clock (Singapore, Kuala
Lumpur), whatever zone the phone is set to, and Today reads the new day's page at that
midnight by itself. The Playwright suite runs the phone in Asia/Singapore at a fixed 10:00
(`fixClock`), and `midnight.spec.ts` crosses midnight on purpose.

**Offline.** The worker precaches the shell on install (the Vite plugin in `vite.config.ts`
lists the built files into it) and answers navigations from the cache when the network is
gone. It never caches `/api`. The app keeps the last Today page per profile in IndexedDB and
renders it first (as today's list, dated), then the fresh one if it can — there is no
spinner either way.

**Two clocks, both fixed, in the end-to-end run.** The phone's clock is Playwright's
(`fixClock`, 10:00 in Singapore on Monday 14 September) and the backend's is frozen at the same
instant: `playwright.config.ts` starts `make dev` itself (`webServer`) with
`NURA_FROZEN_CLOCK=2026-09-14T10:00:00+08:00`, which a dev run installs as `app.clock.FrozenClock`
(answering in UTC) and which refuses to start anything but a dev run. A test that means to cross
the quiet hours or midnight moves it with `POST /dev/clock` (dev runs only) and puts it back.
Locally, a server already on the port is reused; the feed tests check that its clock is frozen
and say so if it is not.

**Dev vs build.** The worker is only registered from the build (Vite does not build it in
dev), so `make web` is for working on screens and the offline behaviour is proven against
`make dev` serving `web/dist`. Over plain http on a LAN address the browser will not
install a worker or offer "add to home screen" — that needs https, which the cloud
deployment brings; on the Mac, `127.0.0.1` counts as secure.

# Nura — the web client

The app the patient opens in Safari and adds to the home screen (ADR 0001). TypeScript in
strict mode, Preact with signals, Vite, CSS custom properties, Vitest for units, Playwright
for the phone-sized end-to-end flow. No UI framework beyond Preact, no CSS framework.

```sh
make web         # dev server on http://127.0.0.1:5173/app/ (proxies /api to make dev); --host for the phone
make build-web   # web/dist, which make dev then serves at http://127.0.0.1:8000/app/
make web-test    # Vitest: strings, refusal map, Today model, the feed's store/cards/playback, the kept pages, the voice, contrast,
                 #         the one player, the taps held offline, the emergency card's copy, the paper batch
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
- `src/onboarding/` — onboarding's logic apart from any screen, all unit-tested: `cloud.ts`
  (which words show, how big, in what order), `about.ts` (the questions and what the answers
  change on the phone), `review.ts` (one decision per review-card field), `plan.ts` (which gap
  cards show), `dates.ts`; `state.ts` is where the session is, in memory only.
- `src/screens/onboarding/` — one file per step: About, Cloud, Asks, ReadBack, Records (the
  prompt, the capture and the review card), Questions, Plan.
- `src/feed/` — the vertical feed (W2, E21): `store.ts` (pages by cursor, prefetch, the kept
  first page, the side actions), `model.ts` (a card as the pager shows it, from the backend's
  item alone), `playback.ts` (Hear on tap: the backend's voice or the spoken twin), `session.ts`
  (one store per profile and key). The screen is `src/screens/Feed.tsx`; Ask is
  `src/screens/Ask.tsx`, answered by E03's `POST /profiles/{id}/ask` (`src/feed/ask.ts`).
- `src/speech/speak.ts` — `speak(card)`: the one seam for the spoken twin.
- `src/visit/` — the visit day (E05-03, E05-04, E02-05, E03-05): `recorder.ts` (the phone's
  `MediaRecorder` behind a small seam: opus in webm where it can, Safari's mp4 where not, a
  screen wake lock, nothing sent from here), `clip.ts` ("Hear what Dr Tan said": the recording
  fetched once, played as a `#t=start,end` fragment and paused at the end), `model.ts` (the
  logistics card and the post-visit card as the backend wrote them, each line with its clip; a
  clip plays through the one player, `src/player/`).
  The screen is `src/screens/Visit.tsx`, opened from Today's *See your next visit*.
- `src/sw/sw.ts` — the service worker; `src/offline/` — its registration, the Today cache, the
  feed's kept first page (`feedCache.ts`), the taps held while offline (`queue.ts`) and the
  emergency card kept on the phone (`emergencyCache.ts`).
- `src/player/` — the one player (E15-07): `player.ts` (a card's spoken twin on the phone's own
  voice, a card's pre-rendered voice from E11, a visit's clip; Play and Pause, three speeds, the
  line being said), `voice.ts` (the app's one instance, his speed kept as `device.speed`). The
  controls are `src/ui/Player.tsx`; `Hear` opens them under itself.
- `src/capture/` — papers from his photos (E18-01): `batch.ts` (the grid, one yes, a review card
  each, nothing kept) and `session.ts`. The grid is `src/screens/PaperBatch.tsx`, used by the
  Papers screen (`src/screens/Papers.tsx`, from Me) and by the sitting's batch step.
- `src/screens/Emergency.tsx` — the emergency card, one tap from Today and Me (E13-01's web half).
- `src/ui/focus.ts` — each new screen starts at its heading, for the screen reader and Tab.

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
lines. Every card has four visible buttons — *Hear*, *Ask*, *Family*, *Not for me* — 56px and more, below the card's lines in normal flow: a card taller than the space above them scrolls its lines inside the card, under a scroll shadow painted behind the text, so nothing is ever drawn over a line; the gate keeps *Hear* and
its one action, *Keep going*. The now card's one action goes to Today, where *Taken* is and
where the backend says which dose is due. *Not for me* posts `dismissed` (E21's engagement
kind; for the owner the backend then holds that kind of card for the day). *Family* posts a
card reference to the family thread (E12) for the kinds the thread can carry — a reading, a
visit — and otherwise says it cannot send the card yet; no card's words are ever posted as a
message. *Ask* sends his question, word for word, to E03's recall (voice mode in his density, text in hers) and shows the answer's cited lines, each under its source line, then the boundary, last. Heard, tapped and
shared are written back only by a key that may write events; *Not for me* is always sent,
and every refusal is said on the screen, never swallowed.

**The Visit screen (E05-03, E05-04, ADR 0006).** The logistics card is the backend's (`GET
…/appointments/{appt}/logistics`): when, where, the chief's note under her name as she wrote
it, who drives him — and, for a key that may give the chief's yes, the roster's person on
duty then with one button, *Yes, Mei drives* — and what to bring. Under it, one big paper
button, *Start recording*. It asks the backend for the notice first: a key that does not
change the visits is refused, then the gate (the RECORDING consent in force); with no consent
in force the owner reads today's words and says *I agree*, and anyone else reads the refusal.
Only then is the notice shown and said (`speak()`, a voice on the phone only) and the
microphone opened, so the recording holds the notice and then the doctor's answer. *Dr Tan
said yes* keeps listening; *Dr Tan said no* throws the audio away on the phone and offers the
notes by hand (E05's typed transcript). A red dot and a timer while it listens; *Stop* is the
one thing that uploads, once, the recorder's own bytes as the body; the tab bar is gone while
listening so nothing leaves the screen by mistake. A hidden page stops at once and says so —
before the doctor's answer the audio is thrown away, after it one tap, *Keep what Nura heard*,
sends it. The post-visit card is the backend's, each line with *Hear what Dr Tan said* when
the recording has that line in it; nothing plays until that tap.

**Voice on tap only.** `feed/playback.ts` hands the one player (above) what to play: it warms (fetches, never plays) the
backend's pre-rendered voice for the card on screen and the two after it
(`GET …/feed/{item}/voice`, E11), and *Hear* plays it inside the tap; when the route is not
there (a plain 404 — it stops asking) or has no voice for the card, it reads the card's
spoken twin through `speak()`, which uses only a voice on the phone. Nothing plays when a
card arrives or when a voice ends, and a card's voice stops when the card leaves the screen.

**The one player (E15-07).** Everything Nura says out loud goes through `player/player.ts`: a
card's spoken twin on a voice that runs on the phone, a card's pre-rendered voice (E11's
`GET …/feed/{item}/voice`, played when the backend has it, the twin when it answers 404), and a
visit's clip. It starts only from a tap — *Hear*, *Hear what Dr Tan said* — and never when a card
arrives or another voice ends; one thing sounds at a time, and leaving the screen (or the card
leaving the pager) stops it. Under the button it opens one big *Play / Pause* (half as tall again
as his target), his speed as three plain choices (*Slower*, *Usual speed*, *Faster*) that the
phone remembers (`device.speed`, like the language and the look), and the transcript — the line
being said — in his body size. A clip is the whole recording played from its start and paused at
its end (the media fragment `#t=start,end`, with the start set by hand when it is ignored),
fetched once per recording. A recording this key may not hear — `OnlyTheFamilyHears`, 403 — shows
the refusal's sentence on the line and no player. The transcript is not a live region: a screen
reader would talk over the voice.

**Taps held offline (E00-08).** *Taken* on a Now card that came from a live read, tapped when the
network has gone, is held on the phone (`offline/queue.ts`, `queue.<profile_id>`) with the moment
he tapped. The card says *You tapped this at 10:05 am. / Nura will send it when the internet is
back.* and the next dose the backend marked due becomes the Now card. When the network is back
(the `online` event, or the next time Today opens) the taps go once each, oldest first, one at a
time, before the page is read again; each leaves the phone's list as soon as the backend has
answered it. `POST …/taken` takes the tap's `taken_at` and writes the dose as taken then, only if
it is today on the region's clock (`TapNotToday`), and writes the same tap once however often it
arrives (ADR 0010). A no is said in the catalogue's sentence for the backend's refusal, and nothing
of the papers stays. Held taps follow the Today page's rules: bound to the key and scope set,
deleted with the rest, gone at the region's midnight. A red word on the feeling strip is never
held; the web has no feeling strip yet (E17), so no feeling tap is held today.

**The emergency card on the phone (E00-08, E13-01).** *Your emergency card*, one tap from Today
(either density) and from Me, reads `GET …/emergency-card` and shows the backend's verified
lines and nothing else; the chief's number and the ambulance's (995 or 999) are the card's data,
as buttons that dial. A big *Print this card* opens the backend's own printable page
(`…/emergency-card.html`) in a new tab for the phone's Print. Both are kept on the phone
(`offline/emergencyCache.ts`, `emergency.<profile_id>`): bound to the key and scope set, deleted
on a refusal, a switch of papers and sign-out — and, unlike Today's page, not at midnight: it is
read again once a day and whenever it is opened with a network, and always says when it was read
(ADR 0010). Past midnight with no network Today shows only *Nura cannot reach your papers right
now.* and this card. A key to the card alone (a neighbour's) opens this card and nothing else: no
Today, no feed, nothing under Me that opens more.

**Papers from photos (E18-01).** A browser cannot scan the photo library, so the web's substitute
is the phone's own picker, many at once (`<input type=file multiple accept=image/*,application/pdf>`),
from Me (*Add papers from your photos*) or in the sitting (*Choose many photos*). The picks are a
grid, every one in to begin with; a tap leaves one out and says so in words. Nothing is sent before
*Send N papers*; then each goes through E02's capture route (`/photos`, a PDF to `/imports`), one
at a time, in order, and each paper says what became of it: a review card to check (*Check this
paper* opens the same review card as the sitting, and only its *Looks right* writes facts), the
backend's own words that a page is not a health paper, a refusal in its sentence, or that it could
not be sent (*Send the rest*). A file is only ever in memory; its picture is an object URL let go
as soon as it is sent, and nothing of a photo is written to the phone.

**Accessibility (E15-04).** VoiceOver and Dynamic Type become, on the web, the page's own
semantics and the browser's text size. Every screen has one `h1` (Today's is the greeting) and
each new screen moves focus to it (`ui/focus.ts`); answers that change the screen are said in a
`role=status` region (the read-back's *Nura will keep that.*, a held tap), refusals in
`role=alert`; toggles carry `aria-pressed`; icons are `aria-hidden` beside their word. Every size is
`rem`, so the browser's text size scales all of it: at 200% on a 360 px phone rows of choices wrap,
pills grow taller and never wider, and nothing runs off the side or is drawn over a line. Contrast
is 7:1 on every decision (`tests/unit/contrast.test.ts`), and a file picker's label shows the focus
ring its hidden input would. Reduce Motion leaves nothing moving. His own large-text setting
(E01's `large_text`, folded into his State's `functional.vision`) makes the writing one step bigger
(`data-text="large"`, 125%) on his own phone, kept for offline, and never on a family member's. The
e2e runs axe (`@axe-core/playwright`) over every screen in both densities and fails on any serious
or critical finding; a demo deployment's banner (ADR 0008) is left to its own checks.

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

## Onboarding (W3)

About you → the word cloud → the papers (the sitting's prompt, photo or PDF, review card, one
yes) → the read-back → the questions the papers raised → the first week → Today, in the order
E01's sitting keeps (`about_you → papers → read_back → questions → closed`). It starts after
*I agree* on the for-me door and after *Set it up* on the for-someone door; *Set up later*
skips it and *Set up Nura* under Me starts it again.

**Every route is live** — E01 (#117) is on main, and nothing is mocked: the e2e runs against
the backend itself, both clocks frozen at 10:00 Singapore.

| Route | From |
|---|---|
| `GET /onboarding/conditions?language=`, `GET` / `PUT /profiles/{id}/settings` | E01 |
| `POST` / `GET /profiles/{id}/biography`, `/biography/papers`, `/biography/read-back`, `/biography/questions`, `/biography/close` | E01; a kept question goes on the next visit's list by E01 itself (E05), or waits and moves when one is booked (`handed_over_to`) |
| `GET /profiles/{id}/plan?language=`, `POST /profiles/{id}/plan/later` | E01 |
| `POST /profiles/{id}/photos`, `POST /profiles/{id}/imports` (a PDF), `POST /profiles/{id}/confirmations` (`review_card`), `POST /profiles/{id}/review-cards/{card}/confirm` | E02 |
| `POST /profiles/{id}/consents/sharing/preview`, `POST /profiles/{id}/consents/sharing`, `POST /profiles/{id}/keys` | E12 (the preview is this PR's backend seam) |

**Whose words.** Every line of the sitting — the step's headline and lines, the read-back, the
questions with their State id and source line, the summary, each prompt — is E01's, in plain
words; the client composes none. E01's script speaks to him, so a chief setting up her father
reads the app's own headings in his name (*A few things about Pa*). E01's writes answer in the
language on his settings; a chief's phone reads the sitting again with `?language=` after each
one, so choosing Malay for him never turns her screens Malay.

**Papers of every kind.** A PDF goes to `POST /imports` (sent as a `share`), anything else
to `POST /photos`; both answer with the same review card. A line Nura could not read shows
the backend's own prompt and an empty box, and is never confirmed as read: what he types is
the correction, or he leaves it out. A card's `notice` lines are shown as the backend wrote
them; a page that is not a health paper has nothing to say yes to. In the patient density
every line of the card has its own Hear (what the line is, what was read, how sure Nura is);
the caregiver density keeps the header's.

**The gap card's actions.** A photo gap opens the camera and a PDF gap the file picker; the
breakfast gap asks that one question of About you and comes back with the gap closed. Which
medicine he is allergic to has no route to write it yet (#117), so that card has *Later* only
— a tap on the cloud's word would close nothing. The invite gap goes to E12's
flow — who, which parts, the words, one *I agree*, then `POST /consents/sharing` and a
caregiver key to the same parts (`POST /keys`). Only on his own papers: the consent route
takes the owner's own yes. The words are never composed here: the client asks
`POST /consents/sharing/preview`, which renders them with the same function the consent keeps
them with — so what he reads is what is kept, word for word — and sends back their version.
He names the person he lets in (*Their name*); the words use only that name, never the account
the number may already be, and it gives way to the person's own when they sign in.

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

## The Record (W5)

One nav entry, *Papers* (the Record: `go({ name: "record", at })`; the tab is *Papers* because
the plain-words verifier refuses "Record" as not his word, and the glossary's word is "your
papers"). Every screen under it is a place in `src/record/places.ts`; the logic apart from any
screen is `src/record/model.ts`, unit-tested (`tests/unit/record.test.ts`); the screens are
`src/screens/record/` — the first screen, his medicines (the list with source and confidence,
the story, a medicine added and checked, "I have more at home."), his visits (the spine's three
anchors and the cursor, an illness and a paper put with it, the directory and the chief's note,
what changed), his blood tests and his day (the trend, the routine, the chief's builder), and his
papers waiting for a yes (on onboarding's own review card). The family's papers (E12-09) are the
Family screen's (W6), not repeated here.

**One thing a screen, or the list.** In the patient density a list is one item a screen with
*This is 1 of N.* and *Next* (the timeline reads the next page by the backend's cursor when he
reaches the end); in the caregiver density it is the whole list, and the day is a table.

**The backend's lines.** Every card line is the backend's: the anchors, what changed, the
story and its voice script, the count and the reorder buttons' own labels, who was asked to
order, the trend and its boundary (shown apart and last), the day. The catalogue names the
screens and buttons and says a few whole lines with a name, a date or a number in a slot.

**Busy until read.** A Record screen says `aria-busy="true"` from its first frame until its
reads are in, so a screen reader waits for the lines and nothing moves under a finger (the
e2e overlap check waits for it too).

**The reorder card (E04-05).** Its two buttons are on the medicines screen and on the feed's
reorder card, labelled with the line's `reorder_actions`: *Ask the family to order.* posts
`…/medicines/{line}/ask-to-order` (the tap is the yes, as Taken is) and shows the backend's
lines; *I have more at home.* asks how many, mints the yes for that number (subject
`count_correction`) and posts `…/medicines/{line}/more`.

**The machine's screen (E02-08).** `src/screens/Reading.tsx` keeps typed entry and adds *Take a
photo of the machine*: `POST …/readings/photo` answers with a review card, shown on onboarding's
review card with the numbers already in their boxes, and one *Looks right* writes the reading.

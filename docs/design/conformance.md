# Board conformance pass

A screen-by-screen check of the built app against the approved board
(`docs/design/nura-concept-board.html`), over `docs/design-direction.md` wherever the two
disagree, per the brief for this pass. Screenshots are real: taken with Playwright
(`web/tests/visual/board-conformance.spec.ts`) at 390×844 against a running dev server with
`NURA_DEMO_SEED=1`, signed in through "Try it as Pa" and "Try it as Mei" — never a synthetic
fixture family — and committed under `docs/design/screens/`.

Status key: **done** — matches the board's element and works with real data; **fixed here** —
changed in this pass to match; **gap** — the board shows something the app does not build, or
builds differently, named so it is not confused with the above.

**Round 2 (board-fidelity-round-2, 2026-09-18):** closes the round 1 gaps below — the topbar
pattern, Home's three tiles, Services' home-care grid, Ask's source chips, and Profile's own
rows — per the owner's decision that the app must look functionally exactly like the board and
every element on it must be a working feature. See "What round 2 fixed", below the per-screen
tables.

## Welcome — `welcome-pa.png`, `welcome-mei.png`

(One screen; Pa and Mei see the same thing before sign-in.)

| Board element | App | Status |
|---|---|---|
| Hero illustration, rounded card | `WelcomeIllustration` | done |
| Heart mark + "Nura" serif wordmark | present | done |
| Two-line serif tagline + sub-line | present, own copy under `docs/plain-words.md` | done |
| Three value tiles (Remember / Share / Prepare) | present, same three, same icons/tints | done |
| "Get started" full-width button | present | done |
| "Already have an account? Sign in" | one phone-number path in place of two (see `Welcome.tsx`'s own note) | done — deliberate simplification, documented in source |
| — (not on the board) | "Try it as Pa" / "Try it as Mei", demo/dev only | added — needed to reach the real seed for this pass; never shown outside a demo or dev run |

`Welcome.tsx`'s own docstring says it was built "as the approved board draws it" — this screen
needed no fixing.

## Home — `home-pa.png`, `home-mei.png`

| Board element | App | Status |
|---|---|---|
| Topbar: menu, "Nura" wordmark, bell | present (`Shell.tsx`'s `topBar={{ variant: "home" }}`) | done |
| — (not on the board) | a profile switcher chip ("P Pa ›") in the topbar | added beyond the board — `Shell.tsx`'s own note: one account can hold several profiles, so whose papers are open is always on screen. Removing it would hide a real, load-bearing control the board's single-profile mock never had to show; kept, even though it costs Home a pixel-exact match to the board's bare topbar. |
| — (not on the board) | an "Ask Nura a question" search bar under the topbar | added beyond the board — the board's own screen 5 ("Ask Nura") shows the *Home* tab as current, meaning the board itself reaches Ask from Home without drawing how; the search bar is that entry point, wired to the real answer engine (see Ask, below) |
| Greeting: "Good morning, Pa 👋" / "How are you feeling today?" + couple illustration | present, plus the real date | done |
| "Daily check-in" card, "Check in" button | present as "How you feel today" / "Tell Nura" | done — different words, same feature (a `@patient` string choice, not re-litigated here) |
| 6-tile grid: Health, Medicines, Connect, Activities, Care services, Guides | Health / Medicines / Connect match the board word for word; the other three are "Things to do" / "Help at home" / "Things to read" | **fixed here (round 2)** — every tile now opens a real, working screen (see below); round 1 only fixed the captions |
| "Add a health report" row | present as "Add a paper" (also takes photos of any paper, not only reports) | done — broader real feature, close wording |
| "Coming up" + one visit card | present as "Next visit", a fuller real card (address status, who is driving, what to bring) instead of the board's one-liner | done — real data, richer than the mock |

**Fixed here (round 2):** the three tiles that round 1 left as honest "not built yet"
placeholders now each open a real, working screen — closing round 1's gap 1 and 2:

- **"Things to do"** opens a new screen (`web/src/screens/Activity.tsx`, place `activity`):
  the same week ring the Health tab shows, and today's steps, water and meals, each a real
  write through PR #235's lifestyle logs (`POST /profiles/{id}/metrics/{kind}`, `POST
  /profiles/{id}/food`) on his own explicit Save or tap — the confirm-flow shape
  `Reading.tsx` already uses, never a value sent while he is still typing.
- **"Help at home"** opens the Services tab, where it lands on the new home-care grid (below).
- **"Things to read"** opens the Services tab, where its Guides section (already real, round
  1) is.

Both "Help at home" and "Things to read" are gated on the same `visits` scope Services itself
needs (`nav.ts`'s `NEEDS`), so a key without it is never shown a tile that would only reach a
tab it cannot open. `screens/Soon.tsx` and the `soon` place are removed: nothing routes to a
"Nura cannot do this yet" screen from Home any more.

## Health — `health-pa.png`, `health-mei.png`

`Health.tsx`'s own docstring says it was built against "3 · Health" in the board.

| Board element | App | Status |
|---|---|---|
| Topbar: back, "Health", calendar | **fixed here (round 2)** — `Shell.tsx`'s `topBar={{ variant: "board" }}`: back opens Home, the calendar icon opens a new blood pressure reading (`go({ name: "reading" })`) | done |
| Ring: doses taken this week ("12/14") | ring present, backend's own count — never a made-up score | done |
| Four metrics under the ring | Steps / Heart rate / Sleep / Water, vs. the board's Blood pressure / Steps / Sleep / Water | done, one substitution — blood pressure has its own card below instead of doubling up in the metric row; an unlogged metric reads "Not written down yet" (real, honest empty state, not faked) |
| "What Nura noticed" insight card | present ("Blood pressure book and sugar numbers"), real reading, real date | done |
| "Next tablet" card, time | present under "Now" / "Your tablets for today", real dose data | done |
| "Today's tip" card | not seen in this seed's feed | gap — conditional on feed content; not confirmed built |

## Connect — `connect-pa.png`, `connect-mei.png`

| Board element | App | Status |
|---|---|---|
| Topbar: back, "Connect", plus | **fixed here (round 2)** — back opens Home, the plus icon opens the Family Keys screen (`go({ name: "family", part: "keys" })`), the same place "Add" on "Your family" already opens | done |
| "Your family" avatars + Add | present (Mei, real seed data; the board's Kit/Siti are sample names, not missing features) | done |
| "Next call" card | present, real (empty: "No call is on your calendar yet.", not faked) | done |
| "Near you" — 3 tiles (Events, Volunteer, Groups) | present as a real, feed-driven list (dengue/haze/local alerts) instead of 3 static icon tiles | done, different presentation — `Connect.tsx`'s own note: "the feed's own local cards … near his area"; real data, not a re-skin worth risking for this pass |
| "Messages" | present, real (empty: "There are no messages yet.", vs. the board's two sample messages) | done — correctly not faked |

## Ask Nura, with the thinking trace — `ask-pa.png`, `ask-mei.png`

| Board element | App | Status |
|---|---|---|
| Message bubbles (his / Nura's) | present | done |
| "What Nura looked at" | present, as a line rather than the board's pill chips — **left unchanged in round 2**, per the brief | done — same information, different chrome |
| Sources as pills ("Medicines", "Visit, 2 Sep") | **fixed here (round 2)** — `ui/kit/Conversation.tsx`'s `Exchange` now renders them with the kit's own `Chip`/`ChipRow` (`ui/kit/Chip.tsx`) instead of a bespoke `.source-chip` span | done |
| The boundary line ("Nura does not decide what is wrong.") | present ("This is not a doctor's advice. Ask Dr Tan.") | done |
| The thinking trace (dots, ticked steps, spinner) | built (`Ask.tsx`'s `StepTrace`, from `Conversation.tsx`) | done — not visible in the screenshot because the fixture answerer resolves before the trace would show; the component itself is wired and covered by its own tests |
| Composer pinned above the tab bar | present, as a form field rather than a floating pill | done |

## Services — `services-pa.png`, `services-mei.png`

| Board element | App | Status |
|---|---|---|
| Topbar: back, "Services", (no icon) | **fixed here (round 2)** | done |
| "Your visits" card + checklist (questions ready, what to bring) | present | done |
| "Care services" — 4 tiles (Nursing at home, Physio, Meals, Transport) | **fixed here (round 2)** — a new "Help at home" grid (`tabs.tsx`'s `HomeCareGrid`), backed by the same provider directory the app's existing "Care services" (doctors and clinics) section reads, told apart by a new `Provider.category` column (migration `0047_provider_category`). Titled "Help at home" rather than the board's "Care services" to avoid colliding with the existing, different feature of that name (the same reasoning round 1 gave for the Home tile's caption) | done |
| "Guides" list | built (`tabs.tsx`'s `GuideBody`, same learning cards as Home), empty for this seed's feed | done, empty for this seed — not a gap |

**"Help at home", in full:** four tiles — Nursing at home, Physio, Meals, Transport — each
showing "Near you" once a provider in that category is on the directory, or the category's own
line ("Keep moving well", …) when none is near him yet; a tap opens the provider directory
(`record/Timeline.tsx`'s `ProvidersScreen`, now takes an optional `category`) filtered to that
category, with a plain "Nura has nothing near you for this yet." when it is empty — never a
dead tap, never a hidden tile. The demo seed (`app/demo_seed.py`'s `_seed_home_care`) adds two
real-looking providers per category, near Pa's own seeded area.

## Profile — `profile-pa.png`, `profile-mei.png`

| Board element | App | Status |
|---|---|---|
| Avatar + name + caregiver line | present | done |
| Language row | present, as selectable pills (English / Bahasa Melayu / …) rather than the board's read-only row + chevron | done — a real control, richer than the mock |
| Text size row | not confirmed in this screen's scroll depth captured | not verified |
| Emergency card, Insurance, "Who can see what" | **fixed here (round 2)** — `ProfileNav` (`ProfileParts.tsx`) carries Emergency, a new Insurance row, Keys, Consents and "Only me" as the Profile tab's own rows (`ListRow`s in `#profile-list`), not tucked in the header's "Me" sheet. The Me sheet (`MeSheet`/`MeBody`, `Me.tsx`) is untouched and keeps working for every caller that still opens it (the header's menu button, `openMe`) — removing that duplicate path is a later change, once every caller has moved to the Profile tab | done |
| "What Nura uses" toggles | present, as full-width On/Off buttons rather than the board's compact row + small switch | done — deliberate: CLAUDE.md's 56pt-target, patient-mode rule takes precedence over the board's small switch control here |
| — (not on the board) | a "days with tablets taken" streak card | added beyond the board — a real, existing feature |
| — (not on the board) | an Insurance row, opening his policies (`screens/Insurance.tsx`) | added beyond the board, gated on the same `money` scope "Insurance letters" already uses — a real feature the board's own mock has no row for |

**Insurance, in full:** the row opens the policy list alone (`GET
/profiles/{id}/insurance/policies`, already on `main`) — insurer, cover type, status, what it
covers, when it renews, when the next payment is due, the policy number, every line the
backend's own words. **The Ledger (claim amounts, #260) is not built here**: #260 was still an
open PR, not merged, when this round started, so its claim-amount data has no backend on this
branch to read honestly. This is the one named gap this round leaves — see below.

## Topbar pattern — resolved (owner's decision, 2026-09-17)

Round 1 named this the one systemic gap: the board draws Health, Connect, Ask and Services
with a per-screen topbar (back arrow, centred title, one contextual icon), where the app used
one global topbar — menu, "Nura" wordmark, the profile switcher, bell — on every screen, per
`docs/design-direction.md`'s "Reference B's top bar" section, which called that global header
a deliberate choice ("on every screen in both densities, not only the caregiver's: one app and
one account").

**The owner's decision (2026-09-17): the board wins.** `docs/design-direction.md`'s "Reference
B's top bar" section is updated to say so. `Shell.tsx`'s `topBar` prop now carries the board's
own topbar on each of the five tab-root screens: `"board"` (back · centred title · one action
icon) for Health, Connect and Services; `"home"` (menu · wordmark · bell, no switcher) for
Home; `"plain"` (a bare title) for Profile. The profile switcher (whose papers are open) is
kept on Home's own topbar — round 1's reasoning for it still holds, and the board's own
single-profile mock never had to draw one — and is now also reachable from the Profile tab's
own "Switch profile" row. Nested screens under a tab (Family, the Record, Emergency, the
vertical feed, Ask, …) are not on the board at all, so they are untouched and keep the old
global header, switcher included: only the five tab-root screens pass `topBar`.

## What round 2 fixed

- `web/src/screens/Shell.tsx`: `topBar` prop and `BoardTopBar` — the board's per-screen
  topbars, on the five tab-root screens only (see above).
- `web/src/screens/Health.tsx`, `Connect.tsx`, `tabs.tsx` (`VisitsScreen`), `Me.tsx`
  (`ProfileScreen`), `Today.tsx` (`DadToday`, `ChiefHome`): each now passes `topBar`.
- `web/src/screens/Activity.tsx` (new): Home's "Things to do", steps/water/meals logging with
  the week ring, real writes through PR #235's lifestyle logs.
- `web/src/screens/HomeParts.tsx`: `DoGrid`'s three tiles wired to real destinations instead
  of `SoonScreen`; `web/src/screens/Soon.tsx` and the `soon` place removed (nothing reaches it
  any more).
- `backend/app/memory/models.py`, `spine.py`, `channels/api/timeline_schemas.py`: a
  `HomeCareCategory` enum and `Provider.category` column (migration
  `0047_provider_category`, after `0046_insurance_policies_claims` — `0047_insurance_claim_amounts`
  from #260 was not on `main` when this branch started, so this chains onto `0046` directly);
  classified in `scripts/data_map.py` and regenerated into `docs/trust/pdpa-data-map.md`.
- `backend/app/demo_seed.py`: `_seed_home_care`, two providers per category near Pa's area.
- `web/src/screens/tabs.tsx`: `HomeCareGrid`, and `CareBody`'s providers now exclude
  categorised (home-care) ones, so the two sections never mix.
- `web/src/screens/record/Timeline.tsx`, `record/places.ts`, `record/model.ts`: `ProvidersScreen`
  takes an optional `category`, filters the same directory, and names an empty category
  plainly instead of hiding the tile.
- `web/src/ui/kit/Conversation.tsx`, `warm.css`: Ask's source lines now render with the kit's
  `Chip`/`ChipRow`.
- `web/src/screens/Insurance.tsx` (new), `ProfileParts.tsx`, `Me.tsx`, `api/nura.ts`,
  `api/types.ts`: the Profile tab's own rows (Emergency, Insurance, Keys, Consents, "Only
  me"), reading the real `GET /profiles/{id}/insurance/policies`.
- `docs/design-direction.md`: "Reference B's top bar" section updated — the board wins over
  the old global-header choice (owner's decision, 2026-09-17).
- `web/src/strings/en.ts`, `ms.ts`, `zh.ts`, `types.ts`: every new patient-facing string above,
  tagged `@patient` and passing `make plain-words` and `make language` in English, Malay and
  Chinese.
- `web/tests/visual/board-conformance.spec.ts`: waits for the home-care grid before the
  Services shot, so it is never taken before that section has drawn.

## Named gaps left after round 2

1. **Profile's Insurance Ledger** (claim amounts, #260): not built — #260 was not merged when
   this round started, so there is no backend to read claim amounts from honestly. The policy
   list itself (insurer, cover, renewal, premium due) is built and real.
2. **Ask's "What Nura looked at"**: left as a line rather than the board's pill chips, per the
   brief — the source chips above it were the requested fix.
3. **Health's "Today's Tip" card**: conditional on feed content; not confirmed present for
   this seed (round 1's finding, unchanged).
4. **Profile's text size row**: not confirmed in this screen's scroll depth captured (round
   1's finding, unchanged).

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
| Topbar: menu, "Nura" wordmark, bell | present | done |
| — (not on the board) | a profile switcher chip ("P Pa ›") in the topbar | added beyond the board — `ShellHeader`'s own note: one account can hold several profiles, so whose papers are open is always on screen, in both densities. Removing it would hide a real, load-bearing control the board's single-profile mock never had to show. |
| — (not on the board) | an "Ask Nura a question" search bar under the topbar | added beyond the board — the board's own screen 5 ("Ask Nura") shows the *Home* tab as current, meaning the board itself reaches Ask from Home without drawing how; the search bar is that entry point, wired to the real answer engine (see Ask, below) |
| Greeting: "Good morning, Pa 👋" / "How are you feeling today?" + couple illustration | present, plus the real date | done |
| "Daily check-in" card, "Check in" button | present as "How you feel today" / "Tell Nura" | done — different words, same feature (a `@patient` string choice, not re-litigated here) |
| 6-tile grid: Health, Medicines, Connect, Activities, Care services, Guides | Health / Medicines / Connect match the board word for word; the other three are "Things to do" / "Help at home" / "Things to read" | **fixed here** (captions only) — see below |
| "Add a health report" row | present as "Add a paper" (also takes photos of any paper, not only reports) | done — broader real feature, close wording |
| "Coming up" + one visit card | present as "Next visit", a fuller real card (address status, who is driving, what to bring) instead of the board's one-liner | done — real data, richer than the mock |

**Fixed here:** the three tiles' captions now say "Stay busy." / "Help at home." / "Read and
learn." — the board's own words — in English, Malay and Chinese (`web/src/strings/en.ts`,
`ms.ts`, `zh.ts`, keys `hub.activitiesLine`, `hub.careLine`, `hub.careLineOther`,
`hub.resourcesLine`). The board's *titles* for these three ("Activities", "Care services",
"Guides") were tried too and reverted: `make plain-words` fails "Activities" as a word he
would have to ask about (rule 3) — the mandatory plain-words gate (CLAUDE.md, non-negotiable)
overrides matching the mock's exact title here. "Care services" and "Guides" as titles are
already used elsewhere in the app (Services tab) for a *different* screen each, so reusing
them for these tiles too would collide; the existing titles ("Things to do", "Help at home",
"Things to read") stay. All three tiles are honest about what is behind them: each opens
`SoonScreen`, which says plainly "Nura cannot do this yet" — **gap, no backend**, and already
not faked.

## Health — `health-pa.png`, `health-mei.png`

`Health.tsx`'s own docstring says it was built against "3 · Health" in the board.

| Board element | App | Status |
|---|---|---|
| Topbar: back, "Health", calendar | global topbar (menu/wordmark/switcher/bell) instead | **gap** — see "Topbar pattern" below |
| Ring: doses taken this week ("12/14") | ring present, backend's own count ("10/25" for this seed) — never a made-up score | done |
| Four metrics under the ring | Steps / Heart rate / Sleep / Water, vs. the board's Blood pressure / Steps / Sleep / Water | done, one substitution — blood pressure has its own card below instead of doubling up in the metric row; "Heart rate" and "Steps" read "Not written down yet" for this seed (real, honest empty state, not faked) |
| "What Nura noticed" insight card | present ("Blood pressure book and sugar numbers"), real reading, real date | done |
| "Next tablet" card, time | present under "Now" / "Your tablets for today", real dose data | done |
| "Today's tip" card | not seen in this seed's feed | gap — conditional on feed content; not confirmed built |

## Connect — `connect-pa.png`, `connect-mei.png`

| Board element | App | Status |
|---|---|---|
| "Your family" avatars + Add | present (Mei, real seed data; the board's Kit/Siti are sample names, not missing features) | done |
| "Next call" card | present, real (empty: "No call is on your calendar yet.", not faked) | done |
| "Near you" — 3 tiles (Events, Volunteer, Groups) | present as a real, feed-driven list (dengue/haze/local alerts) instead of 3 static icon tiles | done, different presentation — `Connect.tsx`'s own note: "the feed's own local cards … near his area"; real data, not a re-skin worth risking for this pass |
| "Messages" | present, real (empty: "There are no messages yet.", vs. the board's two sample messages) | done — correctly not faked |

## Ask Nura, with the thinking trace — `ask-pa.png`, `ask-mei.png`

| Board element | App | Status |
|---|---|---|
| Message bubbles (his / Nura's) | present | done |
| "What Nura looked at" | present, as a line rather than the board's pill chips | done — same information, different chrome |
| Sources as pills ("Medicines", "Visit, 2 Sep") | rendered as one sentence instead | gap (styling only) — not changed in this pass; kit has a `Chip` component that could carry this, flagged as a follow-up |
| The boundary line ("Nura does not decide what is wrong.") | present ("This is not a doctor's advice. Ask Dr Tan.") | done |
| The thinking trace (dots, ticked steps, spinner) | built (`Ask.tsx`'s `StepTrace`, from `Conversation.tsx`) | done — not visible in the screenshot because the fixture answerer resolves before the trace would show; the component itself is wired and covered by its own tests |
| Composer pinned above the tab bar | present, as a form field rather than a floating pill | done |

## Services — `services-pa.png`, `services-mei.png`

| Board element | App | Status |
|---|---|---|
| "Your visits" card + checklist (questions ready, what to bring) | present | done |
| "Care services" — 4 tiles (Nursing at home, Physio, Meals, Transport) | the app's "Care services" section is a *different*, real feature: the list of doctors and clinics he has seen, not home-care categories to book | **gap, no backend** — a naming collision with an existing real feature; the board's four home-care categories do not exist anywhere in the app |
| "Guides" list | built (`tabs.tsx`'s `GuideBody`, same learning cards as Home), empty for this seed's feed | done, empty for this seed — not a gap |

## Profile — `profile-pa.png`, `profile-mei.png`

| Board element | App | Status |
|---|---|---|
| Avatar + name + caregiver line | present | done |
| Language row | present, as selectable pills (English / Bahasa Melayu / …) rather than the board's read-only row + chevron | done — a real control, richer than the mock |
| Text size row | not confirmed in this screen's scroll depth captured | not verified |
| Emergency card, Insurance, "Who can see what" | built, but live in the header's "Me" sheet (opened from the topbar avatar), not the Profile tab the board draws them on | **gap (location)** — reachable, one tap further than the board shows |
| "What Nura uses" toggles | present, as full-width On/Off buttons rather than the board's compact row + small switch | done — deliberate: CLAUDE.md's 56pt-target, patient-mode rule takes precedence over the board's small switch control here |
| — (not on the board) | a "days with tablets taken" streak card | added beyond the board — a real, existing feature |

## The one systemic gap: topbar pattern

The board draws Health, Connect, Ask and Services with a per-screen topbar (back arrow,
centred title, one contextual icon). The app uses one global topbar on every screen — menu,
"Nura" wordmark, the profile switcher, bell — per `docs/design-direction.md`'s "Reference B's
top bar" (`Shell.tsx`'s own docstring: "on every screen in both densities, not only the
caregiver's: one app and one account"). The brief names the board as the source of truth over
`docs/design-direction.md` where they disagree, so this is named here rather than resolved:
rebuilding every tab's header to match the board's back+title+icon pattern would drop the
profile switcher from four of five tabs, which is a bigger product change (and a bigger risk
to the existing test suite) than fits a fast conformance pass. Flagged for the owner rather
than guessed at.

## What was fixed in this pass

- `web/src/strings/en.ts`, `ms.ts`, `zh.ts`: the three Home tiles' captions ("Stay busy." /
  "Help at home." / "Help {patient} at home." / "Read and learn.") now match the board's
  words, with Malay and Chinese twins reusing the same terms already used for "Care
  services" and "Guides" elsewhere in the app (`docs/plain-words.md` rule 13's "term" check).
- `web/tests/visual/board-conformance.spec.ts`: new, takes the screenshots this table points
  to, against the real demo seed.

## Named gaps (no backend, or a real but differently-shaped feature)

1. Home's "Activities" / "Care services" / "Guides" tiles: honest "not built yet" placeholders
   (`SoonScreen`) already — no fake content, just not the board's titles (plain-words blocked
   "Activities"; "Care services"/"Guides" are already spoken for elsewhere).
2. Services' "Care services" 4-tile grid (Nursing at home, Physio, Meals, Transport): no
   backend anywhere in the app; the existing "Care services" section is a different feature
   (his doctors and clinics).
3. Ask's source pills: shown as a sentence, not chips — styling only, a kit component exists
   (`Chip`) but wiring it was not attempted in this pass.
4. Profile's Emergency card / Insurance / "Who can see what": built, but under the header's
   "Me" sheet rather than the Profile tab.
5. The global topbar vs. the board's per-screen back+title+icon pattern (see above) — a
   product decision for the owner, not guessed at here.

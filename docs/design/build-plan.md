# Nura rebuild — scope, sequence, testing and the owner's checkpoints

**What we are building:** the app in `experience-blueprint.html` (this folder), scene for scene. Approved by the owner
on 2026-09-18 and 2026-09-19. The interaction rules are in `README.md`. The engine detail is `build-spec.md`.

**No hour totals in this document.** Earlier estimates were guesses. What is recorded here instead is what was
measured: after each checkpoint, the actual builder time and the number of check rounds it took go in the log at the
bottom.

**Where the owner tests:** always the same place, `http://localhost:8000/app/` on the owner's machine. It runs the last
build that reached a checkpoint, never work in progress. Sign in with "Try it as Pa", "Try it as Mei", or your own
number. Single components can be tried on their own at `http://localhost:8000/app/#/blueprint-kit`.

Everything lands on the `redesign` branch. `main` takes it at checkpoint 8.

## Progress: the fixed list every update counts against

A work package counts as **done** only when it is merged on `redesign` and, where it has a screen, the operator has
checked its screen captures against the blueprint. Percent complete = done packages / 24 (a 24th package, country packs, was added on 2026-09-22 at the owner's request). Packages are not equal in
size, so the percent is a count, not a forecast.

| # | Work package | Checkpoint | State |
|---|---|---|---|
| 1 | The look, the phone frame, the shared components | 1 | Done |
| 2 | Build spec | — | Done |
| 3 | Report data: labels, ranges on results, no blank lines | 2 | Done |
| 4 | Reading screen and report table | 2 | Done (#296; owner loaded his real PDF on 2026-09-22: works; polish and "Your papers" follow in `papers-library`) |
| 5 | Insight engine after a paper | 3 | Done |
| 6 | New Home with the living orb | 3 | Done (#295, third review pass; captures sent to the owner) |
| 7 | Insight screen ("What it means for you") wired after "Looks right" | 3 | Not started |
| 8 | Ask Nura interface | 4 | Not started |
| 9 | Onboarding: Welcome, sign in, who is this for, bubble cloud | 5 | Not started |
| 10 | Health and the Health Analyst screens | 5 | Not started |
| 11 | Medicines screens | 5 | Not started |
| 12 | Visits and costs, Insurance screens | 5 | Not started |
| 13 | For you feed screens | 5 | Not started |
| 14 | Not feeling well, Connect, Mei's Home, Profile | 5 | Not started |
| 15 | Feed database-lock fix, failed searches retried | 6 | Done |
| 16 | Streamed reading: rows as they are read, real page progress | 6 | Not started |
| 17 | Cost of a procedure with no visit booked | 6 | Not started |
| 18 | The inbox for many papers | 7a | Not started: needs owner decisions |
| 19 | The matching engine and its verdicts | 7a | Not started: needs owner decisions and real papers |
| 20 | Policy passport | 7b | Not started: needs real policies |
| 21 | Medicine registry and Add a medicine | 7c | Not started: needs the country decision |
| 22 | Connections and content in context | 7d | Not started |
| 23 | Merge to main, full checks, live pass as Pa and Mei | 8 | Not started |
| 24 | **ASEAN-ready country packs**: one country setting (MY, SG first; TH and others by adding a pack) that tailors the emergency number, the licensed drug register, currency, the trusted publishers, ID format, privacy wording and the region the data lives in | 7 | Not started |

## How every piece is tested before the owner sees it
1. Unit tests for the component or rule.
2. End-to-end browser tests on a fixture server with a frozen clock.
3. The full suite in CI on SQLite and on Postgres, plus lint, plain-words and the three-language check.
4. An independent safety review wherever a person could be harmed: extraction, matching, medicines, policy and money.
5. The operator's own live pass on the test copy with the real model switched on.
6. Then the owner's checkpoint. A checkpoint is passed only when the owner says so. Nothing is built on top of a
   checkpoint that has not passed.

## The sequence, and what the owner validates at each checkpoint

### Checkpoint 1 — The look and the building blocks
**Scope:** the dusk glass look across every existing screen; Figtree and the serif accent bundled into the app; the
orb; the in-place status line with the light sweep; soft word-by-word text; staggered reveal; the action sheet with its
three-state button; range bar and chips; **on the web the whole app sits inside a phone frame** (above 600px wide: a
390px device frame with a bezel, the atmosphere inside it, and every bar, sheet and toast kept inside the frame; on a
real phone it is full-bleed with no frame); the overlapping ring on Health fixed.
No screen is restructured and no wording changes yet.
**You test:** open the app on the web as Pa and walk every tab inside the phone frame. Open `#/blueprint-kit` and try each component.
**Passes when:** it looks like the blueprint's phone; nothing escapes the frame; text is comfortable to read; nothing overlaps; large type still works.

### Checkpoint 2 — Load a paper
**Scope:** blueprint scenes 5, 6, 7. The reading screen with the orb and the real stages changing in place; the report
as one table with range bars; every extracted field properly labelled; blank values fixed; "Check this one" for unsure
lines; one "Looks right".
**You test:** upload one of your own PDFs and one photo.
**Passes when:** every line has a proper name, none is blank, the values match your paper, and you could tell what was
happening the whole time.
**Known limit at this checkpoint:** the read still arrives in one piece after the stages. Rows landing one by one as
they are read is checkpoint 6.

### Checkpoint 3 — What it means, and Home
**Scope:** scenes 8 and 14. Right after you confirm a paper, Nura offers questions for the doctor and keeps them on the
visit. Home becomes one headline, one insight card, the next thing to do, and the way to talk.
**You test:** confirm a paper, keep the questions, go Home.
**Passes when:** Home reflects what you just did, in one sentence, with no boilerplate.

### Checkpoint 4 — Ask Nura
**Scope:** scene 15. Conversation with memory, "looked at" chips, soft streaming, answer cards, actions, drafted
messages in a sheet.
**You test:** your own questions back to back, including insurance and a procedure. Needs your API credits.
**Passes when:** the second question remembers the first, every answer names what it looked at, and it says plainly
when the honest answer is "ask your doctor".
**Known limit:** exclusions and the cost of a procedure with no visit booked arrive at checkpoints 7b and 6.

### Checkpoint 5 — The whole app in the new language
**Scope:** scenes 1–4 and 16–25. Conversation-style onboarding with the bubble cloud; Health; Health Analyst;
Medicines; For you; Visits and costs; Insurance; Not feeling well; Connect; Mei's Home; Profile.
**You test:** a brand-new account from Welcome onward; then Pa; then Mei.
**Passes when:** no screen is left in the old style, in English, Malay and Chinese.

### Checkpoint 6 — Live engine upgrades
**Scope:** the feed database-lock fix, so live web-searched cards and clips are switched back on; failed searches
retried; rows landing as they are read, with real page progress on long papers; the cost of a procedure with no visit
booked. Independent safety review of extraction.
**You test:** open For you with live search on while using the rest of the app; upload a long PDF.
**Passes when:** the app never freezes, and the progress you see is real.
**Needs from you:** the decision on real video inside the app or link out only.

### Checkpoint 7 — One record (four separate checkpoints)
Needs the written spec, **which country comes first**, and **your real papers with names removed**.
- **7a Many papers and matching** (scenes 9, 10). **Whose paper is it?** Every paper is checked against the person before
  anything is filed: the name on it (tolerant of name order, initials, spacing, bin/binti, romanisation; not of a
  different surname), the ID number, date of birth, sex against a sex-specific test, the hospital's patient number
  if seen before, and dates that cannot be right (before birth, in the future). A mismatch is never filed silently
  and never refused silently: Nura asks a plain question ("This paper says Mei Tan. Is it yours, or for someone you
  care for?") and only the person's answer files it, moves it to the right person's record, or sets it aside. Other
  discrepancies (a different date of birth, two strengths of one tablet) are asked about the same way. Rules decide,
  never a model; every decision is audited. You test: a folder including the same paper twice, two blood tests
  from different dates, and a paper with someone else's name. Passes when each gets the right verdict and nothing is
  overwritten.
- **7b Policy passport** (scene 11). You test: your own policy PDF. Passes when every line shows the right page and
  nothing says you are covered, only what the policy says.
- **7c Medicine registry** (scene 12). A medicine can be added by a photo or screenshot of the box, strip or label, or by
  typing or saying it. Each entry records: the name as printed, the real medicine name from the licensed register,
  strength, form, pack size, what it is for in plain words from the register (never made up), dose as written,
  prescriber, pharmacy, date and expiry when printed or told, how it was added with the source kept, status, supply
  left, and the high-risk tag. Nura reads printed text only and never names a medicine it cannot read: a box that
  says only "STATIN 40 mg, 28 tablets" records 40 mg, tablets and 28, and asks which statin it is. You test: a
  prescription, a label photo and a receipt for the same medicine under two names, a box photo with only a family
  name on it, and one medicine typed in. Passes when they become the right entries, the unnamed one asks, and the
  duplicate becomes one medicine and one question for the pharmacist.
- **7d Everything connected** (scene 13). You test: open any result. Passes when every door leads somewhere real.
Independent safety reviews of matching, medicines, and policy and money come before each of these reaches you.

### Checkpoint 8 — Release candidate
**Scope:** everything merged to `main` with every check green; the operator's full pass as Pa and as Mei against all
25 scenes. **You decide:** deploy or not.

## Owner decisions, and the checkpoint each one blocks
1. Country: DECIDED 2026-09-22 — the app is ASEAN-ready by configuration (package 24). Malaysia and Singapore packs are filled and tested first; Thailand and others are added as packs. A Thai pack also needs Thai as a fourth language.
2. Real papers with names removed — blocks 7a, 7b, 7c.
3. Real video in the app or link out — blocks 6.
4. Drawn atmosphere or licensed photography — blocks nothing; can change later.
5. The model behind a public launch (ADR 0017 allows the Claude API for demo and laptop runs only) — blocks a public
   launch after 8, not the build.

## Rules that do not bend
Nothing invented: every thinking line is a stage the engine really reports, and no delay is added for effect. The safety
line appears once per screen. Never a diagnosis; never start, stop or change a medicine — that becomes a question for
the doctor. Body text 15px or larger, contrast 4.5:1. Three languages and the caregiver voice for every sentence.

## Log of what actually happened
| Date | Checkpoint | Builder time measured | Check rounds | Owner's verdict |
|---|---|---|---|---|
| 2026-09-21 | Build started: phase 1, feed lock fix and the spec running | | | |
| 2026-09-21 | Blueprint v3: the Add a medicine scene (photo, screenshot, text or voice) | | | Approved: "yes exactly this" |
| 2026-09-21 | Build spec written (#290) | 12 min | | |
| 2026-09-21 | Checkpoint 6, part: feed database-lock fix (#291) | 52 min | | Operator's live test with real searches on: 300 other requests during a 7-minute run, slowest 0.9 s, none failed, no lock errors. Every search was refused by the API (credit balance exhausted: 3 calls succeeded, 45 refused), and the fix marked the jobs failed and retried them up to three times as designed. Independent review found four things (a pause made mid-search was silently undone; write-time re-checks; no external-processor audit entry for feed calls; failed jobs miscounted in the log); all fixed, each new test first shown to fail on the unfixed code. Required checks green; merged to main and into `redesign` on 2026-09-21. Live search stays off on the test copy until a working API key is back. |
| 2026-09-21 | Checkpoint 2, data: labels, ranges on their results, no blank lines (#292) | 43 min, then 11 min of fixes | | Independent safety review found two defects (sex-specific and reversed ranges taken as certain bounds; a faint range reported as sure). Both fixed; operator re-ran the parser on 20 inputs: all 11 ambiguous ones give no bounds with the text kept, all 9 clear ones parse. Merged into `redesign`. The table screen itself is still to build. |
| 2026-09-21 | Checkpoint 3, engine: the insight after a paper (#293) | 68 min | | Independent safety review: no paper text can reach what Nura says; the model can only choose among checked questions. Two required fixes in progress (a permission check on keeping questions with no visit; the external-processor audit entry on failed model calls, also in the weekly analyst). |
| 2026-09-21 | **Checkpoint 1 ready for the owner**: the look, the phone frame and the shared components (#294) | 99 min, then 12 min for the ring | | Operator's review as Pa: Welcome, Home, Visits and the component gallery match the blueprint inside the frame. First review FAILED on the Health ring still overlapping its text although reported fixed; fixed properly with nine geometry tests and re-checked by eye. 169 browser tests pass inside the frame. On the owner's test copy (without a model key: the operator's own process-group kill took the test server down and the key, held only in that process, was lost). Owner's verdict: pending. |
| 2026-09-22 | Cost: a model per task, a cap of six searches per feed run, a model-call counter (#299, ADR 0018) | about 160 min elapsed on an overloaded machine | | Reading papers and Ask stay on Opus; analyst, search, estimate and drafts on Sonnet; summarising, clips and narration on Haiku. Full backend suite 3,028 passing. Merged; on the owner's test copy. |

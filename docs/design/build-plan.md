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
three-state button; range bar and chips; the app as a phone column on wide screens; the overlapping ring on Health fixed.
No screen is restructured and no wording changes yet.
**You test:** open the app as Pa and walk every tab. Open `#/blueprint-kit` and try each component.
**Passes when:** it looks like the blueprint; text is comfortable to read; nothing overlaps; large type still works.

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
- **7a Many papers and matching** (scenes 9, 10). You test: a folder including the same paper twice, two blood tests
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
1. Which country first — blocks 7a, 7b, 7c.
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

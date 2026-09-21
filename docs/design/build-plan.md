# Nura rebuild — the plan and where it stands

**What we are building:** the app in `experience-blueprint.html` (this folder), scene for scene. The owner approved it
on 2026-09-18 and 2026-09-19 ("Yes it needs to be like this"). Open that file in a browser to see the target. The
interaction rules are in `README.md`. The detailed engine spec is `build-spec.md` (being written).

Everything lands on the `redesign` branch first. `main` takes it when it is whole and every check is green.

Status words: **Running** (a builder is on it now) · **Next** (starts when what it waits for lands) · **Waiting**
(needs the spec, a review, or an owner decision) · **Done**.

| # | Phase | Blueprint scenes it delivers | Hours | Status | Waits for |
|---|---|---|---|---|---|
| 1 | Foundation: dusk glass look across the whole app, bundled fonts, the orb, in-place status line, soft words, staggered reveal, action sheet with three-state button, phone column on wide screens | the look of all 25 | 3 | **Running** (`p1-foundation`) | nothing |
| 2 | Your papers: the reading screen and the report table; every field properly labelled; blank values fixed | 5 Add a paper · 6 Nura reads it · 7 The report table | 5 | Next | phase 1 |
| 3 | Home, and the insight right after an upload | 8 What it means for you · 14 Home | 4 | Next | phase 1 |
| 4 | Ask Nura: conversation, memory, sources, actions, drafted messages | 15 Ask Nura | 3 | Next | phase 1 |
| 5 | Every other screen in the new language, and conversation-style onboarding with the bubble cloud | 1 Welcome · 2 Sign in · 3 Who is this for · 4 What is part of your health · 16 Health · 17 Health Analyst · 18 Medicines · 19 For you · 20 Visits and costs · 21 Insurance · 22 Not feeling well · 23 Connect · 24 Mei's Home · 25 Profile | 15 | Next | phases 1–4 |
| 6 | Engine: streamed reads with real page progress; cost of a procedure with no visit booked; feed database-lock fix and failed searches retried | 6 · 15 · 19 | 11 | **Running** in part (`fix-feed-run-lock`) | the spec, for the rest |
| 7 | **One record** (added 2026-09-19): the inbox for many papers, the matching engine and its six verdicts, the policy passport, the medicine registry, everything connected and content in context | 9 Many papers at once · 10 What changed in your record · 11 Policy passport · 12 Medicine registry · 13 Everything connected | 25–35 | Waiting | the spec (**Running**, `build-spec`), owner decisions, real papers |
| — | Independent safety reviews: extraction, matching, medicines, policy and money | 6 · 10 · 11 · 12 | 6 | Waiting | phases 6 and 7 |
| — | Integration, check rounds and fixes | all | 5 | Waiting | everything |
| — | Live pass as Pa and as Mei, scene by scene against the blueprint | all 25 | 2 | Waiting | everything |
| | **Total** | | **about 80–90** | | |

## Owner decisions that phase 7 and part of phase 6 need
1. Which country first. The app is configured for Singapore; the examples used so far are Malaysian.
2. Real papers with names removed: two or three insurance policies, blood tests from different labs, prescriptions, receipts.
3. Clips: play the publisher's real video inside the app on tap, or link out only.
4. Backgrounds: the drawn atmosphere, or licensed photography.
5. The model behind a public launch. The Claude API is allowed for demo and laptop runs only (ADR 0017).

## Rules that do not bend
Nothing invented: every thinking line is a stage the engine really reports, and no delay is added for effect. The safety
line appears once per screen. Never a diagnosis; never start, stop or change a medicine — that becomes a question for
the doctor. Body text 15px or larger, contrast 4.5:1. Three languages and the caregiver voice for every sentence.

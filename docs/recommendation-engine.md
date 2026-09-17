# The recommendation engine: everything Nura knows, turned into what to do next

**Status: design, 2026-09-17. Docs only; nothing here is built. The core decision is recorded
in `docs/adr/0016-correlation-sits-beside-state.md`. Where this document needs the owner to
choose, it says so in §8 and gives a recommendation.**

## 0. What the owner asked for

> "the core of what i wanted to build was about having users keep check of their meds, their
> history, their insurance, their daily lifestyle, the appointments, their food intake, their
> search history, and based on this and anything else i forgot, becomes a correlative
> recommendation to the user of the app, on reminders, what to prep for when meeting the doc,
> what to prep, personalized reads, personalized video feeds etc"

Nura takes everything it knows about a person and turns it into personalised
recommendations. Every other part of the product serves that.

Today the inputs and the outputs exist, and **nothing connects them.** Each output reads its
own narrow inputs. This document:

1. audits what goes in and what comes out (§1);
2. designs the layer that connects them (§2);
3. makes that layer safe by construction, not by review (§3, §4);
4. says how we know it works (§5);
5. breaks it into stories one builder can each take (§6);
6. lists what the owner must decide (§8).

It changes none of the existing rules. The boundary, plain words, scope, State, the
pharmacist's queue, caps and quiet hours all stay as they are. This layer only adds work
that goes through them.

---

## 1. The audit

Read against `main` at `2c30a3c5`. Every claim names the file it rests on.

### 1.1 The inputs

| Input | Exists? | How complete | Where |
|---|---|---|---|
| **Medicines and doses** | Yes | Strong. Reconciled lines with source, dose codes on routine anchors, every tap with its moment and a stored `late` bit (ADR 0014), counts and reorder dates, interaction pairs from licensed data, the high-risk rule. | `medicines/models.py` (`MedicationLine`, `DoseTaken`), `medicines/service.py`, `medicines/reorder.py`, `drugs/` |
| **History** | Yes | Strong. Facts with provenance and validity windows, events, episodes, papers, the timeline, "what changed", conditions told at onboarding (`condition.<code>` facts), allergies, lab trends against ranges, visit summaries from transcripts, memos in his words. | `memory/`, `ingestion/`, `onboarding/conditions.py`, `reasoning/trends.py`, `reasoning/visits/summary.py`, `reasoning/visits/memos.py` |
| **Insurance** | Partly | Thin. The insurer's name and the policy reference, typed on a yes, under `Scope.EMERGENCY` for the emergency card; a provider can be marked as a hospital on his insurance, used by the red-flag tiers. No coverage, no guarantee letter status, no claims. A fuller record is being built now (`his-insurance`, no code pushed yet). | `insurance/insurer.py`, `memory/models.py` (panel hospital on `Provider`) |
| **Daily lifestyle** | Partly | The routine (wake, three meals, bed as clock anchors; walks; which readings he is asked for), readings typed or photographed (blood pressure, pulse, sugar, weight as facts on a READING event). **Being built now:** logs of steps, heart rate, sleep and water (`health-overview-and-calls`, no code pushed yet). No phone or watch sync (E02-11, T2). | `routines/`, `ingestion/readings.py`, `keys/scopes.py` (`reading:` subjects sit under READINGS) |
| **Appointments** | Yes | Strong. The spine, providers and his directory, calendar proposals under the CALENDAR consent, the brief at T-3, logistics, questions, the consult recording, the summary, memos. | `memory/spine.py`, `memory/providers.py`, `ingestion/connectors/calendar.py`, `reasoning/visits/` |
| **Food intake** | No | Nothing records what he ate. The feed's `FOOD` cards come from a weekly search keyed on his **conditions**, not on his meals. Food logging is being built now (with the lifestyle logs). The food-photo verdict (E09-04) is not built. | `delivery/feed/compose.py` (`FOOD_TERMS`, `_learning`) |
| **Search history** | Kept, never used | **More than "not recorded".** Every question asked through Ask is kept: its words go to the region's object store (`questions/{profile}/{sha256}`) as a `MESSAGE` artefact written under `Scope.ASK`, on the `HOLD_HEALTH_RECORD` consent. The row does not name who asked (the trail does). Nothing lists, reads, deletes or learns from these questions. Web and video searches from the ask bar are **not** kept, on purpose ("The words are not kept"). | `search/ask.py` (`_keep_question`), `delivery/feed/find.py` |

Inputs the owner did not name that the engine should use:

| Input | Exists? | Where |
|---|---|---|
| **How he feels**: cloud taps, the notes they became, the symptom log | Yes | `reasoning/feelings/`, `safety/symptom_log.py` |
| **What he did with what he was shown**: card engagement, "not for me", the format switch, nudge responses | Yes, but only by card *type* and for *today* | `delivery/feed/engagement.py`, `delivery/nudges/models.py` |
| **Gaps**: what the record is missing | Yes | `reasoning/visits/gaps.py`, `onboarding/gaps.py` |
| **Red flags**: the day's hard stop | Yes | `safety/red_flags.py` |
| **His own words**: memos and commitments | Yes | `reasoning/visits/memos.py`, `delivery/nudges/commitments.py` |
| **Family activity**: thread, photos, roster | Yes | `family/` |
| **Where he lives, the season** | Yes | `delivery/feed/local.py`, `Profile.area` |
| **State**: posture, phase (before a visit, after a discharge), preferences | Yes | `state/` |

**One finding that is a promise, not a gap.** When a tap on the feeling cloud is read against
the record, the note tells him "Nura will keep this for your visit to Dr Tan."
(`reasoning/feelings/strings.py`, `NoteOutcome.FOR_THE_DOCTOR`) and names the appointment
(`FeelingNote.appointment_id`). But nothing in `reasoning/visits/` reads `FeelingNote`, and a
cloud tap writes a `SYMPTOM` event, not the `symptom.reported` fact the brief reads
(`symptom_log.symptoms_since`). As far as the code shows, the note is kept but does not reach
the brief or the questions. Story RE-02 fixes it before anything else here is built.

### 1.2 The matrix

Rows are inputs. Columns are the outputs the owner named.

**●** used today · **◐** partly used · **○** should use: the product gap · **—** should
not use, by design (the reason is in the note)

| Input | Reminders (`delivery/triggers/`) | Visit prep (`reasoning/visits/`) | Personalised reads (feed cards) | Personalised video (clip cards) | Nudges (`delivery/nudges/`) |
|---|---|---|---|---|---|
| Medicines, doses, taps | ● dose ladders, morning card, reorder, untapped and late patterns | ● gaps (no purpose, interaction), brief counts | ● explainer and safety jobs per medicine, now card, reorder, proud number | ● explainer clips per medicine | ● pattern (mornings taken), recognition |
| History: conditions, papers, labs | ◐ onboarding prompts, papers waiting for a yes | ● what changed, memos, summaries | ● explainers per condition, story cards, trends in the story | ● explainer clips per condition | ◐ commitment (memos) only |
| Readings (BP, sugar, weight, pulse) | ○ the routine stores which readings he is asked for, at which anchor; no trigger reads them | ◐ brief counts numbers; the trend is not in the brief | ● reading card, story trends | ○ | ◐ blood pressure direction reaches the check-in |
| Insurance | ○ bring the insurance card before a visit or an admission | ○ guarantee letter status (the spec's T-3 brief line) | ○ caregiver only: what the insurance letter is, when an admission is planned | — nothing to watch | — never nudged: money worries are not a nudge |
| Routine (anchors, walks) | ● the clock every trigger runs on; ○ its walks, like its reading prompts, are shown on his day but sent by nothing | ○ | ○ | ○ | ◐ check-in time only |
| Lifestyle logs: steps, heart rate, sleep, water (being built) | ○ a log prompt only where a doctor's memo or a condition makes it matter (E10-04) | ○ counts for the doctor ("sleep written down on 12 nights") | ○ | ○ | ○ recognition of walks, never a target |
| Food intake (being built) | — no meal reminders beyond his routine anchors | ○ patterns with readings, as questions | ○ food cards from what he eats, not only his conditions | ○ food clips | — no food nudges: food is where nagging starts |
| Appointments, providers | ● visit tomorrow, brief at T-3 | ● everything | ● visit, logistics, memo cards | ○ "what happens at a kidney test" before one | ● anticipation |
| Feelings, symptoms | ◐ check-in at the close of his day | ◐ symptom log ● ; cloud notes **not read** (finding above) | ○ | ○ | ● check-in, watched notes |
| Search history | — nothing pushed from what he searched | ○ opt-in: "add this to your questions?", on his yes | ○ opt-in: explainers on what he asked about | ○ opt-in | — never: a nudge arrives unasked, and on WhatsApp others can see it |
| Engagement | ◐ nudge rest after two ignored | — | ◐ format switch, "not for me" for one day, by card type | ◐ clips-to-cards switch | ● dismissals and rests by kind |
| Gaps | ◐ onboarding plan prompts | ● questions from gaps | ● explainer jobs for gaps State shows | ● | — |
| Family activity | ● family notices | ● logistics driver from the roster | ● family photo stories | — | ● presence |
| Area, season | — | — | ● local and seasonal cards | ○ | — (the Context kind is unbuilt) |
| **Correlation across inputs** | ○ | ○ **the core gap** | ○ | ○ | ○ Pattern kind (today it is only a count of mornings) |

Read down any column and the gap is plain: **every "●" is one input feeding one output
through code written for that pair.** No cell uses two inputs together, except the feeling
cloud's inference (a feeling against a new medicine's monograph, or his blood pressure's
direction). The "○" cells are the product. The "—" cells are rules and stay empty.

### 1.3 Is `state/` the right foundation?

**Yes, as the foundation. No, as the place correlation happens.**

State is the right thing for every recommendation to be *rendered from*. It is the one
choke point: every rendered row names a snapshot (`RenderedFromState`); it knows the phase
(before a visit, after a discharge) and the preferences; and "everything downstream ranks
from one thing". A recommendation that did not name a State would break the promise the
whole product rests on.

State is the wrong place to *compute* correlation, for four reasons in the code:

1. **State refuses to judge, and says so as a promise.** `state/dimensions.py`: "No
   threshold on a reading lives here, nothing here decides that a number is high."
   `docs/trust/samd-boundary-review.md` §4 cites that line as the test that proves
   `state_posture` stays informational. A pattern ("higher on days without breakfast") is
   arithmetic, but it compares numbers. Putting it in State breaks the promise the
   regulatory review relies on.
2. **Posture would start to rise from a pattern.** Posture is "the worse of" every
   dimension (`worse_of`). A pattern inside a dimension would move the wash and the order of
   the day. That would be a monitoring loop, which §6 of the SaMD review lists as crossing
   the line.
3. **State recomputes on every fact, in the fact's own unit of work**
   (`recompute_on_fact`). Correlation reads four weeks of series and belongs on the daily
   rhythm, not inside every blood pressure write.
4. **A pattern sits under more than one scope.** State narrows one subject to one scope
   (`_narrowed`, `scope_for_subject`). "Breakfast × blood pressure" is RECORDS *and*
   READINGS, and must be hidden from a key holding only one of them. State has no shape for
   that.

So correlation sits **beside** State, reads the record under a key, writes what it found
**naming the State it was computed against**, and every recommendation built on it is still
rendered through `render_from_state`. The one thing that goes *into* State is what he
decides about the engine: "stop using my food for suggestions" is a Fact he confirms,
folded into the preference dimension, like "not for me" already is.

---

## 2. The architecture

### 2.1 The shape

```
                     the record, read under a key, one scope at a time
   medicines · readings · lifestyle logs · meals · symptoms and feelings · visits ·
   insurance · engagement · asked topics (only with his consent)
                                   │
                    (1) SERIES — app/reasoning/patterns/series.py
                        typed, dated points with the ids they rest on; no judgement
                                   │
            ┌──────────────────────┴───────────────────────┐
            │                                              │
 (2) PATTERNS — app/reasoning/patterns/          State (unchanged) — app/state/
     PatternDetector port → Pattern rows          phase, posture, preferences,
     arithmetic over a reviewed rule catalogue,   "stop using my X" facts
     nightly; each names its State and every      │
     id it rests on                                │
            └──────────────────────┬───────────────────────┘
                                   │
            (3) THE BROKER — app/delivery/recommend/
                RecommendationRule catalogue: (State, series, patterns, asked topics)
                → Candidates, each with `because` (ids), audience, safety class, topic
                Ranker port → one ordered Slate per key per day. Writes nothing.
                                   │
   ┌──────────────┬────────────────┼────────────────┬───────────────────┐
 (4) reminders   visit prep       feed: reads      feed: clips       nudges
   triggers       questions,       compose.py       search jobs →     engine.py
   engine         brief, logistics _learning        clip cards        (Pattern,
                                                                       Curiosity)
   each output takes the candidates of its kind and writes its own row the way it
   already does: templates, the verifier, the boundary line, render_from_state, caps
```

Four rules hold the shape together. Each copies a rule the codebase already keeps
somewhere else.

1. **The broker writes no words and no rows.** Like the retriever (`search/retrieve.py`: "a
   retriever cannot widen what a key reaches and cannot put a sentence in front of him"),
   the broker hands back candidates. The output that shows one owns its words, its checks
   and its row. Nothing ever skips the plain-words verifier, the boundary register, the
   pharmacist's sample or the caps.
2. **Nothing is recommended without `because`.** A candidate has one or more evidence ids.
   Each id resolves to a row on this profile, and the reading key can see every one. A
   candidate with none is refused at construction (`NoEvidence`), not filtered later.
3. **A pattern is a derived row, never a Fact.** A Fact needs an artefact or event under it
   and State folds it. A pattern is an inference. It gets its own immutable table, and
   State never folds it.
4. **Recommendations share the budget that exists.** Two new cards a day, one nudge a day,
   quiet hours, none on a red-flag day. The engine gives the existing slots better things to
   show. It never adds slots.

### 2.2 (1) Series

`app/reasoning/patterns/series.py`. One reader per input family. Each reads under the
caller's key, one scope at a time, the way `feelings/record.read_situation` does. What the
key does not hold is left out and named as withheld.

```python
@dataclass(frozen=True, slots=True)
class Point:
    day: date                  # his local date (REGION_TZ), the unit every rule pairs on
    at: datetime               # UTC
    value: float | str | bool
    ids: Evidence              # fact / event / tap / artefact ids this point rests on

@dataclass(frozen=True, slots=True)
class Series:
    kind: SeriesKind           # BP_SYSTOLIC, BP_DIASTOLIC, SUGAR, WEIGHT, PULSE, STEPS, SLEEP_MINUTES,
                               # WATER_CUPS, MEAL_BREAKFAST, DOSE_ON_TIME(line), FEELING(word), SYMPTOM(code)
    scope: Scope
    points: tuple[Point, ...]
    answered_days: frozenset[date]   # days a person said something, including "no"
```

**`answered_days` is the correctness rule the in-flight log builders must meet.** A day
with no breakfast entry is a day nobody wrote anything down. It is not a day he skipped
breakfast. A rule compares "days with" against "days without" only on days someone
actually answered. Days with no answer are in neither group. So the logs being built now
must let a person say "no breakfast" or "did not walk", as an entry of its own. §2.7 is the
contract for them.

### 2.3 (2) Patterns: where correlation happens

`app/reasoning/patterns/`: `rules.py` (the catalogue), `detect.py` (the port and its
adapters), `models.py` (the `Pattern` table), `service.py` (the nightly run).

**The port.**

```python
class PatternDetector(Protocol):
    def detect(self, series: Mapping[SeriesKind, Series], rules: Sequence[PatternRule],
               *, window: DayWindow) -> Sequence[Found]: ...
```

It never reads the database. It never writes a word. It returns `Found` values: rule id,
the two groups with their days and numbers, the evidence ids, and a suppression reason or
none.

**The rule catalogue** is data, and reviewed data, like the allowlist and `HAZARDS`:

```python
@dataclass(frozen=True, slots=True)
class PatternRule:
    id: str                     # "breakfast_bp_morning"
    version: int
    exposure: SeriesKind        # MEAL_BREAKFAST (yes/no per day)
    outcome: SeriesKind         # BP_SYSTOLIC, the morning reading
    pairing: Pairing            # SAME_DAY | NEXT_MORNING
    window_days: int = 28
    min_days_each: int = 5      # at least 5 answered days in each group
    noise_gate: float           # the smallest difference in the outcome's unit worth saying
    tier: Tier                  # A: lifestyle × readings; B: touches a medicine (memo only)
```

**The first catalogue** (three rules, tier A, pending decision D6):

| Rule | Exposure | Outcome | Pairing | Noise gate |
|---|---|---|---|---|
| `breakfast_bp_morning` | breakfast yes/no | systolic, morning | same day | 5 mmHg |
| `sleep_bp_morning` | slept under 6 hours / 6 or more | systolic, morning | next morning | 5 mmHg |
| `walk_sugar_fasting` | walked yes/no (routine walk, or steps logged) | fasting sugar | next morning | 0.5 mmol/L |

**The default adapter, `RuleDetector`, is arithmetic and nothing else:**

1. Pair exposure and outcome days by the rule's pairing. Only days where both were answered
   count.
2. Leave out every day with a red flag, and every day in the fortnight after a discharge.
   Those days are not his usual days.
3. Two groups. Each needs `min_days_each` days, or the pattern is `too_few_days`.
4. The difference between the two group averages must be at least the `noise_gate`, or
   nothing is found.
5. **Split-half consistency.** Split the window into its first and second fortnight. The
   difference must point the same way in both, or it is `not_consistent`.
6. Suppression checks, in this order. A high-risk medicine (`safety/high_risk.py` classes)
   is active and the outcome is a reading → `high_risk_medicine` (memo only; see §3.4). He
   turned the signal off → `signal_off`. The rule is resting after two dismissals →
   `resting`.

It uses no p-value, no correlation coefficient and no probability. These are the reasons,
and they are safety reasons, not shortcuts:

- The samples are tiny (5 to 28 days). A coefficient over them looks precise and is not.
- A number like "r = 0.7" or "80% sure" is a probability about his body. That is an
  individualised risk score, which SaMD review §6 lists as crossing the line.
- Split-half consistency and a small, reviewed catalogue control false findings in a way a
  pharmacist can read and check. The null test in §5.2 measures the false-finding rate for
  every rule before it ships.

The noise gate is not a threshold on a reading. It never says a number is high. It says a
*difference between his own two groups* is too small to mention. It is set from how much a
home cuff or a glucometer varies between readings, and it gets its own row in the SaMD
review (story RE-11).

**The table.** `Pattern` is immutable, superseded and never edited:

```
pattern(id, profile_id, rule_id, rule_version,
        scopes JSON           -- every scope an input was read under, e.g. ["records","readings"]
        window_from, window_to, computed_at,
        state_id FK state_snapshot   -- the State it was computed against
        groups JSON           -- [{"label":"with","days":6,"average":132.0},{"label":"without","days":5,"average":141.0}]
        evidence JSON         -- {"facts":[...],"events":[...],"taps":[...]}
        suppressed_because    -- null | too_few_days | not_consistent | high_risk_medicine | signal_off | resting
        valid_to              -- window_to + 14 days
        supersedes_id, superseded_at)
```

Suppressed patterns are kept and shown on the caregiver's list as suppressed, with the
reason, because `.claude/rules/safety.md` says so. They are never shown to him.

**One door.** `patterns.service.readable(session, context)` returns only rows where
`context.allows(scope)` holds for **every** scope in `scopes`. A test fails on any other
`select(Pattern)` (the ADR 0004 decision 10 pattern). The route matrix in
`tests/test_row_scope.py` registers the new routes.

**When it runs.** In the delivery engine's run (`delivery/triggers/engine.run_due`), under
the acting context the run already opens: a new step, `_patterns`, once per local day,
after `_flags` and before `_hand_over_nudge`, so a nudge can use it that day. The brief's T-3
step also asks for a fresh run for that profile. It never runs inside a fact write. It
follows ADR 0005: no scheduler of its own.

**What is rule-based now and model-backed later.** Detection stays rule-based. A model
does not choose which of his numbers to compare. The catalogue is the allowlist of
comparisons (§2.6).

### 2.4 (3) The broker

`app/delivery/recommend/`: `models.py`, `rules.py`, `broker.py`, `rank.py`.

```python
class OutputKind(StrEnum):
    REMINDER = "reminder"            # a bring-line, a log prompt
    VISIT_QUESTION = "visit_question"
    BRIEF_LINE = "brief_line"
    READ = "read"                    # a learning / food / story card topic
    CLIP = "clip"
    NUDGE = "nudge"                  # Pattern, Curiosity

class SafetyClass(StrEnum):
    RECORD_BACK = "record_back"      # says his own record back: no boundary line needed
    PATTERN = "pattern"              # Surface.PATTERN: memo and caregiver by default (§3.4)
    EXTERNAL = "external"            # allowlisted content: Surface.LEARNING_CARD

@dataclass(frozen=True, slots=True)
class Evidence:
    kind: str                        # fact | event | tap | pattern | appointment | line | asked_topic | engagement
    id: uuid.UUID
    scope: Scope

@dataclass(frozen=True, slots=True)
class Candidate:
    rule_id: str
    output: OutputKind
    topic: TopicCode                 # from the topic catalogue (§2.5)
    because: tuple[Evidence, ...]    # never empty: __post_init__ raises NoEvidence
    safety: SafetyClass
    audience: frozenset[Audience]    # PATIENT, CAREGIVER, MEMO
    private_to: uuid.UUID | None     # set for anything resting on search history
    base: int                        # the rule's weight
    boosts: tuple[str, ...]          # codes, for Why.boosts
```

**`broker.slate(session, *, context, state, day) -> Slate`** reads the series, the readable
patterns and, only with consent, the asked topics. It runs the `RecommendationRule`
catalogue, drops every candidate whose `because` the key cannot fully read, ranks the rest,
and returns them grouped by `OutputKind`. It writes nothing. It is audited like any read.

**The first recommendation rules.** Phase 1 needs nothing new to be logged.

| Rule | When | Candidate |
|---|---|---|
| `new_medicine_explainer` | a line started in the last 14 days | READ and CLIP on that medicine, boosted ahead of older topics |
| `feeling_after_new_medicine` | a cloud tap in the last 7 days whose word the new medicine's monograph lists | READ on that feeling with that medicine (the reviewed learning content), and the note into VISIT_QUESTION (fixes the §1.1 finding) |
| `visit_topic_week` | BEFORE_VISIT phase, and a trend on that visit's provider kind moved since the last visit | READ and CLIP on that test ("what your kidney test measures") |
| `test_coming` | a paper or a visit names a test in the next 7 days | CLIP on what happens at that test; REMINDER bring-line if the paper names fasting |
| `bring_insurance` | an admission or a procedure is on the spine within 7 days, and an insurer is on record | REMINDER bring-line (patient); caregiver line on letter status once the insurance record has it |
| `pattern_found` | a readable, unsuppressed `Pattern` | VISIT_QUESTION (memo), a caregiver card; NUDGE Pattern only under decision D1 |
| `logged_for_doctor` | BEFORE_VISIT and lifestyle logs exist | BRIEF_LINE with counts only ("You wrote down your sleep on 12 nights.") |
| `asked_about` | an asked topic in the last 30 days, consent in force | READ and CLIP on the topic, `private_to` him; VISIT_QUESTION *suggestion* that needs his yes |

**Ranking.** The `Ranker` port: `rank(candidates, *, state, engagement) -> list[Candidate]`.
The default `RuleRanker` is a fixed table:

- base weight by rule;
- **+20** when the evidence is from the last 7 days;
- **+15** in `BEFORE_VISIT` when the topic belongs to that visit;
- **+10** once when a topic of his was opened or played in the last 30 days;
- **−15** for each "not for me" on that topic in the last 30 days;
- a topic dismissed twice rests for 30 days (the nudge engine's rest rule, per topic).

These numbers become the feed's `priority` and `Why.boosts`. They never move a card across
a section of the supply, never past the gate, and never past a cap.

**Learning from dismissals is counting his own taps at read time.** "Nothing trains on
user data" (CLAUDE.md) forbids a model trained on his engagement or anyone else's. The
per-person adjustment is the arithmetic above, recomputed each read, the way
`nudges/engine.py` counts dismissals today.

### 2.5 Topics

`app/delivery/recommend/topics.py`: one catalogue of `TopicCode`s. The codes cover
conditions, generic medicines (through the licensed register, `_generic_of`), tests,
feelings, lifestyle and food groups. Each code has its search terms in three languages and
a `sensitive` flag.

The `TopicTagger` port maps free text (a question he asked, a meal he typed, a page's text)
to topic codes:

- `KeywordTagger`, the default: phrases per code in en, ms and zh, like `KeywordRetriever`;
- `FixtureTagger` for tests, keyed by sha256 like `FixtureRetriever`.

A text that tags only `sensitive` codes produces no topic, whatever the consent (§3.5).

### 2.6 How each output consumes it

Each output changes in one place and keeps its own rules.

| Output | Where it changes | What it takes | What it writes, as today |
|---|---|---|---|
| Reminders | `delivery/triggers/engine.py`: one step reads `slate.of(REMINDER)` | bring-lines, log prompts | `Delivery` rows through the existing ladder, caps and quiet hours; the rule id on the row |
| Visit prep | `reasoning/visits/questions.py`: new `QuestionSource.PATTERN`, `QuestionSource.FEELING`, `QuestionSource.ASKED`; `brief.py` takes `BRIEF_LINE` | pattern questions (template), the feeling note, suggestions he accepts | `Question` rows with `source_ids` = evidence ids; a PERSON-confirmed row for ASKED |
| Reads | `delivery/feed/compose.py` `_learning`: `wanted` gains the slate's READ topics, each job's `reason.fact_ids` = evidence ids | topics | SearchJobs → cards via `create_item`; `Why` gains `rule` and `pattern_id` |
| Clips | the same jobs with `media="video"` preferred | topics | clip cards (`clips.py`), unchanged |
| Nudges | `delivery/nudges/engine.py`: `_pattern` reads `slate.of(NUDGE)` as well as the mornings count; new `NudgeKind.CURIOSITY` (docs/smart-nudges.md §1, unbuilt) | a pattern (under D1), a topic of this week | `Nudge` rows, one a day, rest rules unchanged |
| Caregiver list | `CardType.PATTERN`, `DeliverTo.CAREGIVER` | patterns, including suppressed ones with the reason | a `FeedItem`, in the caregiver's voice (her catalogue, never his "you"; #210) |
| Health tab (design direction) | "Health Insights" and "Today's Tip" read the feed's own cards of type READING, STORY, LEARNING, PATTERN | — | nothing new: a view of existing cards |

**`FeedItem.private_to`** (new, nullable person id). A card resting on search history is
his alone. `rank._visible_to` drops it for anyone else, so it never reaches the caregiver's
list, "Sent to Pa this week" or the memo. A caregiver holding `Scope.ASK` is no exception
(§3.5).

### 2.7 The contract for the logs being built now

So correlation can read the lifestyle and food logs without changing them later:

1. **Every entry is an Event, with Facts resting on it.** `occurred_at` is when it happened
   on his day, not when it was typed. It gets the source channel, and the device when there
   is one.
2. **Numbers sit under READINGS.** Steps, sleep minutes, water cups and heart rate use the
   `reading:` prefix or a named subject in `keys/scopes.py` (pending decision D4).
3. **Meals are one fact per meal slot.** Subject `meal`, attribute `breakfast | lunch |
   dinner | snack`. The value holds what he said, plus `had: true | false`. **"No
   breakfast" is an entry**, not a missing one.
4. **Days are his local days** (`REGION_TZ`), the unit every rule pairs on.
5. **Nothing is inferred at write time.** No "healthy meal" flag, no score. The food-photo
   verdict (E09-04) is a separate story that reads licensed food-composition data, never a
   model's guess.

### 2.8 What is rule-based now, and what can be model-backed later

| Part | Now | Later, behind the same port | Never |
|---|---|---|---|
| Series | code | — | — |
| Pattern detection | `RuleDetector`: arithmetic over the catalogue | a new *rule* in the catalogue, reviewed and null-tested like the first | a model choosing which numbers to compare or what they mean |
| Pattern sentence | templates | — | model-written: the numbers are the content |
| Topic tagging | `KeywordTagger` | `ModelTagger`: an in-region model, zero retention, no training on inputs. Most useful for Malay and Chinese food names and free-text questions. | — |
| Recall retrieval | `KeywordRetriever` | model retriever (already planned) | — |
| Compression of pages | fixture | grounded model (already planned) | uncited output |
| Ranking | `RuleRanker` table | a generic relevance scorer of a card's text against a topic, not trained on any user | a model trained on engagement |
| Food composition | — | a licensed food-composition table (Malaysian and Singapore tables) | a model's nutrition estimate |
| Safety class, audience, routing | code | — | anything but code |

Each port gets a conformance suite in the pattern of `tests/voice_conformance.py`, and two
adapters run through it.

---

## 3. How it stays safe

These are constraints the code enforces. Each one names the test that holds it.

### 3.1 Correlation is not causation, and Nura does not diagnose

- **A new inferring surface, `Surface.PATTERN`,** in the boundary register
  (`safety/boundary.py`), with words in three languages. What Nura did: "Nura noticed this in
  your own numbers." The same two last sentences as every surface. A row in
  `docs/trust/samd-boundary-review.md` §4. `render_from_state` refuses a pattern row without
  the line (`NoBoundaryLine`). This mechanism exists; this is one more entry.
- **Pattern sentences are templates, held to a whitelist, not a blacklist.** This is the
  `DO_NOT_STOP` approach (`plain_words._keep_taking_pattern`). A pattern card has exactly
  this shape:
  1. what he did on some days and his number then;
  2. the same for the other days;
  3. "This is what your own numbers show. It does not say why." (fixed);
  4. who does the next thing ("Nura put it on your questions for Dr Tan.");
  5. the boundary.

  Example, in English, for him:

  > On 6 mornings you had breakfast. Your blood pressure was about 132.
  > On 5 mornings you had no breakfast. It was about 141.
  > This is what your own numbers show. It does not say why.
  > Nura put it on your questions for Dr Tan.
  > This is not a doctor's advice. Ask Dr Tan.

  The verifier gets a `pattern` rule set that fails a line with:
  - a cause word: because, so, makes, causes, due to, leads to, sebab, kerana, menyebabkan,
    因为, 导致, 所以;
  - a grade: high, low, good, bad, normal, too, tinggi, rendah, 高, 低, 正常;
  - a condition's name;
  - an instruction verb: eat, skip, stop, start, take, sleep more, makan, berhenti, 吃, 停.

  `tests/test_boundary.py` and a new `tests/test_pattern_words.py` walk every template in
  every language.
- **A pattern never moves State.** `Pattern` is not a `Fact`. No hook writes to
  `semantic.after_fact_write`. `tests/test_state.py` gains "a pattern row changes no
  posture". A pattern never starts a ladder, never raises a flag and is never computed from
  a live stream. The nightly run is the only writer.
- **The question for the doctor is the product, not the card.** Every unsuppressed pattern
  becomes a `QuestionSource.PATTERN` question. The template is "My blood pressure was
  higher on mornings I had no breakfast. Is that worth talking about?" It names the numbers
  and not a conclusion (SaMD residual risk 2).

### 3.2 It never tells him to start, stop or change a medicine

- **Tier B rules** (a medicine's timing, or a tap late or missing, against a reading or a
  feeling) go to `MEMO` only. They never produce a card or a nudge for him, and never a
  caregiver card that could be forwarded to him. The broker sets the audience. The output
  cannot widen it (`tests/test_recommend_audience.py`).
- **A high-risk medicine suppresses every reading-outcome pattern for the patient and the
  caregiver**, including tier A. Warfarin, insulin, digoxin, methotrexate or an opioid is
  on his active lines, from `safety/high_risk.py`'s own classes. "Sugar higher on days
  without a walk" beside insulin invites a changed dose. Those patterns go to the memo
  only, and show on the caregiver list as `high_risk_medicine`.
- **Every read, clip and question passes the treatment-change checks that exist:**
  `compress.changes_treatment`, `health_words.names_medicine_or_dose`, and the reroute to
  a doctor's question. Nothing new is exempt.
- **No recommendation names an amount.** The same test as `tests/test_call_clinic.py`
  ("no card names an amount") runs over every template in `recommend/` and `patterns/`.

### 3.3 No `why`, no recommendation

- `Candidate.because` is non-empty by construction (`NoEvidence`).
- Every output row carries the ids: `FeedItem.why` (`fact_ids`, `pattern_id`, `rule`),
  `Nudge.reason`, `Question.source_ids`, `Delivery.rule`.
- **The why he reads** is rendered from those ids into plain lines, in his voice or the
  caregiver's: "You wrote down breakfast on 11 days and your blood pressure on 14 days."
  The web "Why am I seeing this" sheet shows those lines, each linking to the thing
  (story RE-08).
- **Property test** (§5.2): for every candidate the broker returns over the fixture
  profiles, every evidence id resolves on the profile and is readable by the key.

### 3.4 Unreviewed clinical content is labelled honestly

The owner has decided to seek no clinical sign-off for now. The design does not pretend
otherwise.

- **Every rule, every pattern template and the topic-to-content map go into the
  pharmacist's queue** (ADR 0007) as `ReviewKind.RULE` and `ReviewKind.TEMPLATE` items. The
  first fifty renderings of `PATTERN` cards and pattern questions are sampled,
  de-identified, like every card (`REVIEWED_TYPES` gains `PATTERN`).
- **Until a rule and its template are approved, everything it produces carries a line of
  its own:** "A pharmacist has not checked this yet." (ms and zh with it). The line sits
  above the boundary. This follows the precedent on interaction pairs
  (`medicines/strings.py`: "A pharmacist has not checked this pair yet."). The line is
  structure: `create_item` refuses a `PATTERN` row from an unapproved rule without it, and
  the approval state is read at render, so approval takes the line off the next rendering
  without a code change.
- **Patterns ship behind `NURA_PATTERNS=1`**, the way the red-flag tiers ship behind
  `NURA_RED_FLAG_TIERS=1`. Without the flag, the detector still runs and writes rows, so
  the caregiver list and metrics can be tested on fixtures. No pattern is rendered to
  anyone. Backlog E16-03 says "Written review signed off before any flag ships", and SaMD
  question 6 (E09-03) is open. Whether the flag is ever set for a real family without that
  sign-off is the owner's call (decision D2). This document does not make it.

### 3.5 Search history: a new use of personal data

What someone searches about their own health can reveal more than their record does.
Today his Ask questions are kept for recall, under the consent to hold his record. Using
them to recommend is a **new purpose**, and PDPA purpose limitation (in both Singapore and
Malaysia) says a new purpose needs its own consent. **Flag for counsel:** add to
`docs/trust/pdpa-data-map.md` §9.

**The consent.**
- A new `ConsentPurpose.SEARCH_HISTORY`. The wording lives in `consent/texts.py`, in three
  languages, versioned, words kept on the row.
- **Explicit and off by default.** Asked once, on a screen of its own, never bundled into
  onboarding. "No" is as large as "Yes". Asking is never a condition of using Ask.
- **Given by the owner only, basis `OWNER`.** No chief, steward or LPA may give it for him.
  It is about his private curiosity, and nobody else's agreement stands in for his. A
  profile with no owner who can agree has no search history, and loses nothing it needs.
- **Revocable in one tap** (`withdrawal.APP_STOPS` gains it). The stop lines say what
  stops: "Nura stops using what you ask to choose what to show you."
- Proposed words (en), for the plain-words review and a native speaker's pass:
  > Nura can remember what you ask about.
  > Then Nura can show you things about it.
  > Only you see this. Your family does not.
  > You can see the list and delete it any time.

**What is kept, and for how long** (pending decision D3):
- **Topics, not words.** When he asks, the `TopicTagger` turns the question into topic
  codes. An `AskedTopic` row keeps the code, the day, `asked_by_person_id` and the question
  artefact's id. Nothing else.
- **Topics expire after 90 days**, deleted by the nightly run. A recommendation can only
  rest on a topic less than 30 days old.
- **Sensitive codes are never kept.** A question that tags only sensitive codes is
  answered as today, and no topic row is written: sexual health, a mental-health crisis,
  HIV and other infections people are stigmatised for, pregnancy, abuse, end of life. The
  list is data, reviewed by the pharmacist and the owner (decision D3f).
- **No backfill.** Questions asked before consent are never tagged.
- **Web and video searches** from the ask bar stay unkept by default. If the owner decides
  to include them (D3d), only their topic codes are kept, under the same consent.
- **The words already kept.** Every Ask question's text is kept today with no end date. This
  design recommends 90 days for those as well, with or without the new consent. That changes
  existing behaviour, so it is decision D3e, story RE-18.

**Who sees it.**
- **Only him.** `AskedTopic` has one door: `asked.service.mine(context)` returns rows where
  `asked_by_person_id == context.person_id` and the consent is in force. A chief holding
  every scope reads nothing, and a test says so. No `Scope` is added, so no role preset and
  no "only me" mark can reach it by mistake.
- **Everything derived is his alone:** `Candidate.private_to` → `FeedItem.private_to`.
  Never on the caregiver list, the family thread, WhatsApp, the memo or "Sent to Pa this
  week". Never a nudge, never a reminder.
- **Into the doctor's questions only on his yes.** "You asked about your kidney number
  twice. Add it to your questions for Dr Tan?" creates a `QuestionSource.ASKED` question
  only on his confirm (`keys/confirm.py`). Once it is his question, it is visible like any
  question he typed. The confirm screen tells him that.
- **Caregivers' own questions** are not kept as history in this design (decision D3c).

**He can see it.** Profile → "What you asked about": each topic in plain words with the
day. Delete one. Delete all. Stop. Deleting a topic deletes the row now, and any card
resting on it expires at once.

### 3.6 He stays in control

| Control | Built as | Learns |
|---|---|---|
| See why | the Why sheet from evidence ids (§3.3) | — |
| Dismiss | "Not for me" on the card becomes a **topic** decline fact for 30 days, on top of today's decline for that card type for the day | the topic's weight −15; two in 30 days rests the topic; a pattern rule dismissed twice rests for that profile for 30 days |
| Switch a signal off | Profile → "What Nura uses": food, sleep, steps, water, what you ask. Each switch is a Fact `signals.<family> = off`, confirmed by him, folded into State's preference dimension. The detector and the broker skip that series. | immediate: the next run makes no pattern from it, and the patterns it made are superseded as `signal_off` |
| Stop search history | the consent withdrawal (§3.5) | topics deleted |

He sets the switches, or his chief does under the confirm rules that bind every preference
fact today. The search-history consent is his alone.

### 3.7 Caregivers

- A caregiver sees a recommendation only when her key reads **every** scope in its evidence
  (the one-door rule, §2.3). A viewer holding READINGS but not RECORDS sees no
  breakfast × blood pressure pattern.
- Her lines come from the caregiver catalogue, in her voice (the caregiver-voice rule,
  #210). They are never his "you".
- Her list shows suppressed patterns with the reason. His feed never does.
- Nothing `private_to` him reaches her, whatever her scopes.

### 3.8 Plain words, the boundary last, three languages

Every template in `patterns/` and `recommend/` is tagged `@patient` or caregiver, lives in
en, ms and zh, and passes `make plain-words` and `make language`. It uses the glossary's
words ("your blood pressure", never "reading" or "log"). The boundary is the last line, or
the pharmacist line then the boundary. The new `pattern` verifier rules run in all three
languages.

---

## 4. The safety review this owes

Before `NURA_PATTERNS` is set anywhere a real family is:

1. `docs/trust/samd-boundary-review.md`: a §4 row for `pattern`; §6 amended to name the noise
   gate as a limit on reporting a difference, not a threshold on a reading; question 6
   rewritten against this design.
2. `docs/trust/pdpa-data-map.md`: the `pattern` and `asked_topic` tables classified, plus the
   `SEARCH_HISTORY` purpose, its lawful basis, retention and how it stops (the generated
   inventory test fails until they are there).
3. The `clinical-safety-reviewer` subagent on RE-09 to RE-14 and RE-15 to RE-17, as CLAUDE.md
   requires for anything touching consent or `safety/`.

---

## 5. How we know it is good

### 5.1 What "good" means

A recommendation fails in one of four ways:

- **Wrong:** the pattern is not in his data.
- **Unsafe:** it reads as a diagnosis or an instruction.
- **Useless:** nobody acts on it.
- **Annoying:** it is dismissed, or it crowds out the tablet card.

Each has a different check.

### 5.2 "Correctly derived from this data": the tests

**Golden profiles** (`backend/tests/fixtures/recommend/`). Seeded 28-day records: meals,
readings, sleep, taps, one visit. Each has an expected `patterns.json` (rule, groups, day
counts, averages, evidence ids) and an expected `slate.json` (candidates by output, in
order). The test builds the profile through the real write paths, runs the nightly step,
and compares. Five to start:

1. a real breakfast difference;
2. the same with only 4 no-breakfast days (`too_few_days`);
3. a difference in the first fortnight only (`not_consistent`);
4. insulin on the list (`high_risk_medicine`);
5. food switched off (`signal_off`).

**Properties**, run over every golden profile and over profiles generated from seeds with the
standard library's `random` (no new dependency):

| Property | Test |
|---|---|
| **Sufficiency** | Rebuild the series from *only* the pattern's evidence ids and detect again: the same pattern, the same numbers. Nothing it says rests on data it does not cite. |
| **Necessity** | Remove the evidence for one group's days below `min_days_each` and detect again: no pattern. |
| **Order-free** | Shuffle the points: the same result. |
| **Unanswered is not "no"** | Delete every "no breakfast" entry (leaving the days blank): no "without" group, no pattern. |
| **Scope** | For each key preset and each single-scope key: `readable()` returns a pattern only when the key holds every scope in it; the broker returns no candidate citing anything unreadable. |
| **Private** | With consent, a chief, a caregiver with ASK and a viewer see no `private_to` card on any route in `tests/test_row_scope.py`. |
| **No evidence, no candidate** | Constructing a `Candidate` with empty `because` raises. |
| **Nothing moves State** | Posture and every dimension are identical before and after a nightly run. |
| **Words** | Every template × language passes the verifier, and fails when a cause, grade or instruction word is put in. |

**The null test, per rule, in CI.** 1,000 seeded profiles with exposure and outcome drawn
independently (realistic day-to-day variation, 20–28 answered days). The rule may find a
pattern in **at most 2%** of them. A rule over that does not enter the catalogue. This is
the false-finding rate, measured, not argued.

**The power test, per rule.** 1,000 seeded profiles with a true difference of twice the
noise gate. The rule should find it in at least 70%. A rule under that is too strict to be
worth shipping. That is a product call, not a safety failure, and the test reports it
rather than failing.

**Conformance suites** for `PatternDetector`, `TopicTagger` and `Ranker`
(`tests/pattern_detector_conformance.py` and siblings). `RuleDetector` and
`FixtureDetector` both pass the detector's suite. A future adapter must too.

**A replay harness**, `make recommend-replay`. It runs the engine over the demo fixtures
(ADR 0008) for 28 simulated days on the frozen clock and writes each day's slate as JSON.
The PR shows the diff. A change to a weight or a rule is reviewed by what it changes on real
fixture days.

**A checkpoint walk** in `docs/checkpoints.md`. Log a fortnight, see the pattern on the
caregiver list and in the doctor's questions, dismiss it, switch food off, and see it gone.

### 5.3 Measures in use

Counts only, per week, per rule and per topic, kept in region and read by the owner and his
chief, in the shape of `delivery/nudges/metrics.py`. No words, no ids, nothing to an
analytics vendor.

| Measure | Reads as |
|---|---|
| Pattern questions kept on the questions card until the visit vs removed by a person | **useful**, the main one: a caregiver removes what is wrong or silly |
| Reads and clips opened, played or "asked more", by rule | useful |
| "Not for me" by rule and topic; rules and topics resting | annoying; a rule over 40% dismissed across the pilot pauses for review |
| Candidates held by caps, by output | crowding (a health signal, as the nudge spec says, not a failure) |
| Tablet-card action rate before and after the engine is on | **the guard**: if it falls, the engine is crowding out what matters, and the ranker's weights are wrong |
| Patterns suppressed, by reason | where logging is too thin to say anything |
| Signals switched off, search consent withdrawn | trust |

The pharmacist's sample of the first fifty pattern renderings is the check on **unsafe**.
The caregiver's removals are the check on **wrong**, because she knows him.

---

## 6. The build plan

One story, one builder, one branch. **Risk:** low / medium / high, as the issues are
labelled. **∥** marks stories that can run at the same time as the others in their wave.
Every story's acceptance line is its test.

### Wave 0: before anything else

| ID | Story | Acceptance | Risk | Depends on | ∥ |
|---|---|---|---|---|---|
| **RE-01** | Evidence and Candidate types, `NoEvidence`, `readable_by(context)` for multi-scope evidence, `FeedItem.private_to` + `_visible_to` rule (migration) | an empty `because` raises; a card `private_to` him is on no other person's route in `test_row_scope.py` | medium | — | ∥ |
| **RE-02** | The feeling note reaches the visit: `QuestionSource.FEELING` from `FeelingNote(FOR_THE_DOCTOR)` on its appointment, and the brief lists it beside the symptom log | a cloud tap read against a new medicine appears on that visit's questions and brief, citing the note | medium | — | ∥ |
| **RE-03** | Series readers for what exists: doses (on time / late), readings, symptoms, cloud taps, appointments, engagement; `answered_days` | a golden profile's series match the fixture; a key without READINGS gets no reading series, named as withheld | low | — | ∥ |
| **RE-04** | Topic catalogue and `TopicTagger` port: `KeywordTagger`, `FixtureTagger`, conformance suite, sensitive flag | every condition and generic on the demo fixtures maps to a code in en/ms/zh; a sensitive-only text yields no code | medium | — | ∥ |
| **RE-05** | "What Nura uses" switches: `signals.<family>` preference facts, folded by State (`SUBJECT_DIMENSION`), API and a Profile screen | switching food off is a confirmed fact, State's preference dimension shows it, the route is on the trail | medium | — | ∥ |

### Wave 1: connect what exists (no new data, no patterns)

| ID | Story | Acceptance | Risk | Depends on | ∥ |
|---|---|---|---|---|---|
| **RE-06** | The broker v1 and `RuleRanker`: rules `new_medicine_explainer`, `feeling_after_new_medicine`, `visit_topic_week`, `test_coming`; conformance suite for `Ranker` | golden slates match; every candidate's evidence resolves and is readable | medium | RE-01, RE-03, RE-04 | |
| **RE-07** | The feed consumes the slate: `_learning`'s `wanted` from READ and CLIP candidates; `Why.rule`, `Why.boosts`; topic-level "not for me" for 30 days | a new medicine's explainer and clip lead the learning supply that week; a dismissed topic comes back no sooner than 30 days; caps unchanged (existing cap tests green) | medium | RE-06 | ∥ |
| **RE-08** | The Why sheet on web: evidence ids rendered as plain lines, his voice and hers, three languages | every card's why names what it rests on in words; `make plain-words` and axe pass | low | RE-01 | ∥ |
| **RE-09** | `NudgeKind.CURIOSITY` from this week's top READ topic | at most one nudge a day still holds; a curiosity nudge cites its topic's evidence; the rest rules apply | low | RE-06 | ∥ |

### Wave 2: the new logs and insurance (after the in-flight work lands)

| ID | Story | Acceptance | Risk | Depends on | ∥ |
|---|---|---|---|---|---|
| **RE-10** | Series for meals, steps, sleep, water, heart rate; the §2.7 contract checked by test | "no breakfast" is an answered day; a blank day is not | medium | the lifestyle and food logs PR; D4 | ∥ |
| **RE-11** | Insurance into the slate: `bring_insurance` reminder; caregiver letter-status line | an admission 5 days out with an insurer on record yields the bring-line T-1; nothing about money reaches his feed | medium | the insurance PR; D5 | ∥ |
| **RE-12** | `logged_for_doctor` brief lines: counts of what he wrote down since the last visit | the brief says "You wrote down your sleep on 12 nights." and never an average or a judgement | low | RE-10 | ∥ |

### Wave 3: patterns (the correlation)

| ID | Story | Acceptance | Risk | Depends on | ∥ |
|---|---|---|---|---|---|
| **RE-13** | `PatternDetector` port, `RuleDetector`, `FixtureDetector`, the three tier-A rules, conformance suite, the null and power tests | null ≤ 2% per rule over 1,000 seeds; the five golden profiles; sufficiency and necessity properties | **high** | RE-03, RE-10; D6 | ∥ |
| **RE-14** | `Surface.PATTERN`: boundary words in three languages, pattern templates, `pattern` verifier rules (whitelist), the pharmacist line, SaMD §4 row | every template passes in every language; a cause, grade or instruction word fails; a row without the line is refused | **high** | — | ∥ |
| **RE-15** | The `Pattern` table (migration), the one door, the nightly `_patterns` step in `run_due`, supersession, expiry, suppression kept | nothing moves State; a single-scope key reads no two-scope pattern; the step is idempotent per day | **high** | RE-01, RE-13 | |
| **RE-16** | Patterns to the doctor and the caregiver: `QuestionSource.PATTERN`, `CardType.PATTERN` (caregiver, memo), tier B and high-risk to memo only, behind `NURA_PATTERNS` | flag off: rows written, nothing rendered; flag on: a question and a caregiver card with evidence and the pharmacist line; insulin on the list → memo only | **high** | RE-14, RE-15 | |
| **RE-17** | Rules and templates into the pharmacist's queue (`ReviewKind.RULE`, `TEMPLATE`); approval lifts the line at render; `PATTERN` in `REVIEWED_TYPES` | an unapproved rule's card carries the line; approving it removes the line on the next rendering with no deploy | medium | RE-14 | ∥ |
| **RE-18** | *Only on decision D1.* A pattern card or nudge for the patient himself | the same gates as RE-16; the patient's two-cards-a-day cap holds | **high** | RE-16; D1, D2 | |

### Wave 4: search history (only on decision D3)

| ID | Story | Acceptance | Risk | Depends on | ∥ |
|---|---|---|---|---|---|
| **RE-19** | `ConsentPurpose.SEARCH_HISTORY`: words in three languages, owner-only basis, grant and withdraw, PDPA data map rows | a chief or steward is refused; withdrawing deletes every `AskedTopic` row at once | **high** | D3 | ∥ |
| **RE-20** | `AskedTopic`: tagging on Ask (and on find if D3d), the one door, sensitive codes never kept, 90-day purge, "What you asked about" screen with delete | a chief with every scope reads none; a sensitive question writes no row; day 91 has no row | **high** | RE-04, RE-19 | |
| **RE-21** | `asked_about` rule: private reads and clips; the "add to your questions?" suggestion on his yes | the card is on no other person's route; the question exists only after his confirm | medium | RE-06, RE-20 | |
| **RE-22** | Retention of the Ask questions already kept (D3e) | per decision; the recall trail still resolves or says the question has gone | medium | D3e | ∥ |

### Wave 5: quality

| ID | Story | Acceptance | Risk | Depends on | ∥ |
|---|---|---|---|---|---|
| **RE-23** | Recommendation measures (§5.3), counts only, owner and chief; a rule over 40% dismissed pauses itself for review | no words, ids or reasons in the payload; the trail has the read | low | RE-07, RE-16 | ∥ |
| **RE-24** | `make recommend-replay` and the checkpoint walk | 28 frozen days of slates on the demo fixtures; the walk passes | low | RE-07, RE-16 | ∥ |

### Later: model-backed adapters (external)

| ID | Story | Risk | External |
|---|---|---|---|
| RE-25 | `ModelTagger` behind `TopicTagger` | medium | an in-region model provider with zero retention and no training on inputs, in both SG and MY regions |
| RE-26 | Food composition behind a port, for food cards and the food verdict (E09-04) | medium | a licensed Malaysian and Singapore food-composition table |

### Order at a glance

```
Wave 0:  RE-01  RE-02  RE-03  RE-04  RE-05            (all parallel)   RE-14 can start here too
Wave 1:  RE-06 → RE-07, RE-08, RE-09                   (07/08/09 parallel)
Wave 2:  RE-10, RE-11 (when their inputs land) → RE-12
Wave 3:  RE-13 (needs RE-10) ∥ RE-14 → RE-15 → RE-16 → RE-18 (decision)    RE-17 after RE-14
Wave 4:  RE-19 → RE-20 → RE-21     RE-22 whenever D3e is made              (needs D3 first)
Wave 5:  RE-23, RE-24
```

Value arrives at Wave 1: explainers and clips chosen from what changed, the feeling note
reaching the doctor, and a why on everything. Waves 1 and 2 need no new safety surface.
The correlation (Wave 3) is the highest risk and waits on D2.

### External dependencies

- **The in-flight work:** the lifestyle and food logs, and the fuller insurance record
  (Wave 2 blocks on both).
- **A pharmacist's hours** for the rule catalogue, the templates, the sensitive-topic list
  and the first fifty renderings.
- **The regulatory adviser's answer to SaMD question 6**, before patterns reach a real
  family, if D2 says so.
- **Counsel** on PDPA purpose limitation for search history (both countries).
- **A native speaker's pass** on the ms and zh templates, as for every catalogue.
- Later: **an in-region model provider** (RE-25), **licensed food-composition data**
  (RE-26), and phone and watch health sync (E02-11) for automatic steps and sleep.

---

## 7. What this does not do

- It does not diagnose, grade a number, score his health or give a probability.
- It does not add a notification. It fills the slots that exist.
- It does not train anything, on anyone.
- It does not tell the family what he searched for.
- It does not let a model pick what to compare, write a pattern, or touch a medicine.

---

## 8. Decisions for the owner

Each has a recommendation. None is built until it is made.

**D1. Do patterns reach him, or only his doctor and his chief?**
*Recommendation:* the doctor's questions and the caregiver's list only, for the pilot. He
sees a pattern as a question on his own questions card, in his words. A pattern card in his
feed is RE-18, later, if the pilot's removals say the patterns are right.

**D2. May patterns go live for a real family before a clinician or the regulatory adviser
has signed off?**
Backlog E16-03 says "Written review signed off before any flag ships". You have decided
to seek no clinical sign-off for now. These conflict.
*Recommendation:* build all of it. Keep `NURA_PATTERNS` off for real families until SaMD
question 6 is answered. Run it on the demo fixtures and your own family's data with the
pharmacist line on every rendering.

**D3. Search history.**
- a. Collect it at all? *Recommendation:* yes, as opt-in topics.
- b. Default? *Recommendation:* off; asked once, on its own screen.
- c. Whose? *Recommendation:* the patient's own questions only. Caregivers' questions about
  him are not kept as history.
- d. Web and video searches too? *Recommendation:* no for now; Ask questions only.
- e. The Ask question text kept today, with no end date: keep, or delete after 90 days?
  *Recommendation:* 90 days for everyone. It is kept today under the record consent for
  recall only.
- f. The sensitive topics never kept: *recommendation* in §3.5, to settle with the
  pharmacist.
- g. Backfill from questions already asked? *Recommendation:* no.

**D4. Which part of the record the new logs sit under.** This decides who in the family
sees them, and the in-flight builder needs it now.
*Recommendation:* steps, sleep, water and heart rate under READINGS (a viewer and a
caregiver see them, like his blood pressure). Meals under RECORDS (the helper, who may cook
for him, does not see what he ate unless her key is widened).

**D5. Insurance: which part of the record, and what may be recommended from it.**
Today the insurer sits under EMERGENCY, which every key holds.
*Recommendation:* the fuller record (coverage, letters, claims) under MONEY. He is told
only "bring your insurance card". Letter status and anything about cost goes to his chief.

**D6. The first pattern rules.**
*Recommendation:* the three tier-A rules in §2.3. No tier-B rule (a medicine's timing
against a reading) until D2 is settled, and then to the doctor's questions only.

**D7. The budget.**
*Recommendation:* no new slots. Two new cards and one nudge a day stay the cap, and the
engine competes for them.

# ADR 0016 — Correlation sits beside State, not inside it; every output takes its recommendations from one broker

**Date** 2026-09-17 · **Status** proposed · **Decided by** the design builder, for the owner ·
**Stories** E09-02, E09-03 (and RE-01 to RE-24 in `docs/recommendation-engine.md`)

## Context

The owner's product is personalised recommendations drawn from everything Nura knows:
medicines, history, insurance, daily lifestyle, appointments, food, search history. The
recommendations are reminders, visit prep, reads, video and nudges.

Every one of those outputs exists, and each reads its own narrow inputs through code
written for that one pairing (`docs/recommendation-engine.md` §1.2). Nothing correlates
across inputs. The feed ranks by card type and State. The nudges rank by kind and State.
The questions come from gaps, memos and flags.

State (`app/state/`) is the closest thing to a unified model: six dimensions, recomputed on
every fact, and "everything downstream ranks from one thing". The obvious move is to
correlate inside State. This ADR records why we do not, and where correlation goes instead.

Four facts in the code decide it:

1. **State promises not to judge.** `state/dimensions.py`: "No threshold on a reading lives
   here, nothing here decides that a number is high." The SaMD boundary review (§4, row
   `state_posture`) cites that promise as what keeps the posture informational. A pattern
   compares his numbers across days.
2. **Posture is the worst of the dimensions** (`worse_of`). A pattern inside a dimension
   would move the wash and the order of his day from a correlation. That is a monitoring
   loop, which review §6 says crosses the line.
3. **State recomputes inside every fact write** (`recompute_on_fact`, same unit of work).
   Correlation reads weeks of series and belongs on the daily rhythm.
4. **A pattern sits under more than one scope** ("breakfast × blood pressure" is RECORDS
   and READINGS). State narrows one subject to one scope (`_narrowed`) and cannot hide a
   two-scope finding from a one-scope key.

## Decision

1. **Correlation is a reasoning layer beside State:** `app/reasoning/patterns/`. It reads
   series from the record under a key, one scope at a time. It runs a reviewed catalogue of
   pattern rules through a `PatternDetector` port, and writes immutable `Pattern` rows. The
   default adapter is arithmetic only: two groups of his own answered days, a minimum of days
   in each, a noise gate on the difference, and the same direction in both halves of the
   window. It computes no probability and no coefficient.
2. **A pattern is not a Fact, and State never folds it.** A `Pattern` row names the State it
   was computed against (`state_id`), every scope it read (`scopes`) and every id it rests on
   (`evidence`). It is read through one door that requires the key to hold **every** scope
   it names. No posture, ladder or flag ever reads it.
3. **What he decides about the engine does go into State.** "Stop using my food for
   suggestions" is a Fact he confirms (`signals.<family>`), folded into the preference
   dimension, as "not for me" already is. So the one thing everything ranks from still
   carries his controls.
4. **One broker, `app/delivery/recommend/`, turns State, series, patterns and (with consent)
   asked topics into candidates.** Every candidate has `because`, one or more evidence ids;
   construction refuses an empty one. Each candidate also carries an audience, a safety class
   and a topic. A `Ranker` port orders them. The broker writes no words and no rows, the way
   the retriever does not (`search/retrieve.py`).
5. **Each output takes the candidates of its kind and writes its own row as it does today.**
   Triggers, questions and brief, the feed's learning supply and clips, and the nudge engine
   each do this. Templates, the plain-words verifier, the boundary register,
   `render_from_state`, the pharmacist's sample, caps and quiet hours all apply unchanged.
   Recommendations compete for the slots that exist. They add none.
6. **Rule-based now; model-backed only behind ports, and only where a model cannot decide
   anything clinical.** A model may later tag free text to topic codes, retrieve and
   compress, each in region, with zero retention and no training. A model never chooses
   which of his numbers to compare, never writes a pattern's sentence, and never sets a
   candidate's audience or safety class. Per-person learning is counting his own taps at
   read time, because nothing trains on user data.
7. **Patterns render behind `NURA_PATTERNS=1`,** with their own boundary surface
   (`Surface.PATTERN`). Until a pharmacist approves the rule and its template, every
   rendering carries "A pharmacist has not checked this yet." Whether the flag is set for a
   real family before the regulatory adviser answers SaMD question 6 is the owner's decision
   (D2 in the design).

## Consequences

- State's docstring, its SaMD row and its tests stay true without change. `tests/test_state.py`
  gains one assertion: a nightly pattern run changes no posture and no dimension.
- A second derived table joins the snapshot. It needs a migration, a row in the PDPA data
  map, a route in `tests/test_row_scope.py`, and a test that fails on any `select(Pattern)`
  outside its door (the ADR 0004 decision 10 pattern).
- The delivery engine's run (`run_due`) gains a once-a-day `_patterns` step, between the
  flags and the nudges. There is still no scheduler of its own (ADR 0005).
- A card resting on search history needs `FeedItem.private_to`, because a single `scope`
  cannot say "his alone" when caregivers hold `Scope.ASK`.
- The in-flight lifestyle and food logs must record "no breakfast" as an entry, not as a
  missing one. Otherwise no pattern can tell a skipped meal from an unwritten one
  (`docs/recommendation-engine.md` §2.7).
- Correlation runs up to a day behind the record. That is intended: non-real-time is part of
  the boundary.

## Alternatives considered

- **A seventh State dimension for patterns.** Breaks decision facts 1 to 4: a judgement in
  State, posture moved by it, weeks of series inside every fact write, and no way to hide a
  two-scope finding. Rejected.
- **Patterns as Facts with a derived confidence state.** A Fact needs an artefact or event
  under it, and State folds every Fact (`dimension_of` defaults to CLINICAL), so a pattern
  would land in the clinical dimension. Rejected.
- **Each output correlates for itself** (the feed its own, the brief its own). This is what
  exists today, and it is why nothing is joined up. Five copies of the scope and evidence
  rules would drift. Rejected.
- **A model that finds correlations over the whole record.** It would choose comparisons
  nobody reviewed, over tiny samples, and report findings a pharmacist cannot check. It
  moves toward an individualised risk score. Rejected. New comparisons enter as reviewed,
  null-tested rules.
- **Statistical significance (p-values, coefficients).** Meaningless at 5 to 28 days, and
  a number that reads as a probability about his body. Rejected for split-half consistency
  plus a measured false-finding rate per rule in CI.

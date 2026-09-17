"""Feeling inference (E17-02): a tap and its one answer, read against the record.

Three things are read, and only these (the story's own list):

- **Medicines.** A medicine started in the last fourteen days whose licensed monograph lists
  this feeling as a watch-out, by the registry's rule id (`WATCH_OUT_WORDS`). The pharmacology
  is the registry's; the sentence is a template's.
- **His blood pressure.** For the words the cloud ties to pressure (a headache, dizzy), a
  direction the arithmetic shows: his last three numbers, each higher than the one before
  (`record.rising`). Never a threshold, never "high".
- **This week.** A discharge or a visit in the last seven days.

What comes out is a note: a headline, at most two things to tell the doctor — what he said
and when, then the first thing it was read against — who does the next thing, and the
boundary line last (`Surface.FEELING_INFERENCE`). It names no condition and never says to
start, stop or change a medicine. Where the thing it was read against is a medicine, the two
lines after it say not to stop that medicine himself and to tell the doctor how he feels
(`DO_NOT_STOP`, #157): a medicine is never named on the note without them. The templates are
fixed and the tests read every one of them for it. A red word never reaches this module: the caller sends it to the red-flag path, and
there is no note.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.keys.context import KeyContext
from app.medicines.strings import PLAIN_NAME, say_date
from app.reasoning.feelings.models import NoteOutcome
from app.reasoning.feelings.record import Situation, local_date, rising
from app.reasoning.feelings.strings import DO_NOT_STOP, NOTE_HEADLINE, REASON, TELL_ON, THEN
from app.reasoning.feelings.words import (
    NEW_MEDICINE_WINDOW,
    TIMELINE_WINDOW,
    TREND_WORDS,
    WATCH_OUT_WORDS,
    Answer,
)
from app.safety.boundary import YOUR_DOCTOR, Surface, boundary_line
from app.safety.plain_words import Finding, verify
from app.safety.red_flags import Feeling, is_red

MAX_LINES = 2
"""At most two things to tell the doctor on one note (E17-02)."""


class NoInference(ValueError):
    """A red word, or "Fine today": there is nothing to infer, and nothing is."""


@dataclass(frozen=True, slots=True)
class Found:
    """One thing the tap was read against: a code, the ids, and the line that says it."""

    code: str
    ids: dict[str, Any]
    line: str
    doctor: str | None = None
    """For a medicine: the doctor named on its label, if the spine names no visit."""
    medicine: str | None = None
    """For a medicine: his name for it, for the `DO_NOT_STOP` lines said after this one."""


@dataclass(frozen=True, slots=True)
class Composed:
    """A note, composed and not yet written."""

    language: str
    headline: str
    said: str
    lines: tuple[str, ...]
    then: str
    boundary: str
    voice: tuple[str, ...]
    reasons: tuple[dict[str, Any], ...]
    outcome: NoteOutcome
    appointment_id: uuid.UUID | None

    def failures(self) -> list[Finding]:
        found = verify(self.headline, self.language, "headline")
        for line in (*self.lines, self.then):
            found.extend(verify(line, self.language, "line"))
        return [finding for finding in found if finding.severity == "fail"]


def _sentence(line: str) -> str:
    return line[:1].upper() + line[1:]


def read_against(
    word: Feeling, situation: Situation, context: KeyContext, code: str
) -> list[Found]:
    """What on the record this tap reads against, most specific first."""
    now = situation.now
    found: list[Found] = []
    for line in sorted(situation.lines, key=lambda one: one.started_at, reverse=True):
        if now - line.started_at > NEW_MEDICINE_WINDOW or line.plain_name_id is None:
            continue
        rules = [rule for rule in line.watch_out_ids if WATCH_OUT_WORDS.get(rule) is word]
        if not rules:
            continue
        medicine = PLAIN_NAME[code][line.plain_name_id]
        text = REASON[code]["new_medicine"].format(
            medicine=medicine,
            date=say_date(local_date(line.started_at, context), code),
        )
        ids: dict[str, Any] = {
            "line_id": str(line.line_id),
            "generic": line.generic,
            "watch_out": rules[0],
        }
        found.append(
            Found(
                "new_medicine",
                ids,
                _sentence(text),
                doctor=line.prescriber,
                medicine=medicine,
            )
        )
        break
    if word in TREND_WORDS:
        trend = rising(situation.readings, now)
        if trend:
            text = REASON[code]["reading_trend"].format(count=len(trend))
            ids = {"fact_ids": [str(reading.fact_id) for reading in trend]}
            found.append(Found("reading_trend", ids, _sentence(text)))
    discharged = situation.discharged_at
    if discharged is not None and now - discharged <= TIMELINE_WINDOW:
        text = REASON[code]["discharge"].format(
            date=say_date(local_date(discharged, context), code)
        )
        found.append(Found("discharge", {"since": discharged.isoformat()}, _sentence(text)))
    elif situation.recent_visit is not None:
        visit_id, at = situation.recent_visit
        text = REASON[code]["visit"].format(date=say_date(local_date(at, context), code))
        found.append(Found("visit", {"visit_id": str(visit_id)}, _sentence(text)))
    return found


def compose_note(
    word: Feeling, answer: Answer, situation: Situation, context: KeyContext, code: str
) -> Composed:
    """The note for this tap and answer, from templates, with the boundary last."""
    if is_red(word) or word is Feeling.FINE or word not in TELL_ON[code]:
        raise NoInference(f"{word} is not read into a note")
    found = read_against(word, situation, context, code)
    visit = situation.next_visit
    doctor = (visit.doctor if visit else None) or next((f.doctor for f in found if f.doctor), None)
    who = doctor or YOUR_DOCTOR[code]
    # Day-anchored (PR #233 review): the day he answered, fixed here, true however long after
    # this a question row or the brief replays it — never "today" or "since yesterday" (which
    # `TELL`, the cloud's own reply, still says, said once and never replayed).
    said = _sentence(
        TELL_ON[code][word].format(doctor=who, date=say_date(local_date(situation.now, context), code))
    )
    shown: list[str] = [said]
    for f in found[: MAX_LINES - 1]:
        shown.append(f.line)
        if f.medicine is not None:
            # A medicine named on his note is never without these two (#157).
            shown.extend(
                _sentence(line.format(medicine=f.medicine, doctor=who))
                for line in DO_NOT_STOP[code]
            )
    lines = tuple(shown)
    if found:
        outcome = NoteOutcome.FOR_THE_DOCTOR
        # A visit on the spine: the brief and the questions for it read this note (RE-02), so
        # the promise it is kept "for" that visit is true by construction. With no visit to
        # attach it to, nothing reads it there later, so the words say what actually happens
        # instead — he tells the doctor himself, not Nura for him.
        then = (
            THEN[code]["for_the_doctor"].format(doctor=who)
            if visit is not None
            else THEN[code]["for_the_next_visit"].format(doctor=who)
        )
    else:
        outcome = NoteOutcome.WATCH
        then = THEN[code]["watch"]
    headline = NOTE_HEADLINE[code].format(doctor=who)
    boundary = boundary_line(Surface.FEELING_INFERENCE, code, doctor=doctor)
    reasons = tuple(
        {"code": f.code, "shown": index < MAX_LINES - 1, **f.ids} for index, f in enumerate(found)
    )
    return Composed(
        language=code,
        headline=headline,
        said=said,
        lines=lines,
        then=then,
        boundary=boundary,
        voice=(headline, *lines, then, *boundary.splitlines()),
        reasons=reasons,
        outcome=outcome,
        appointment_id=None
        if visit is None or outcome is not NoteOutcome.FOR_THE_DOCTOR
        else visit.appointment_id,
    )

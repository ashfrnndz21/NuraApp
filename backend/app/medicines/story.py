"""The medication story: what it is for, how to take it, what to watch, what to avoid, and
what to do if he forgot — rendered from templates, in his language, as a card and a script.

Every sentence comes from `app.medicines.strings`, chosen by the rule ids the licensed
registry put on the monograph and by the dose the label said. Nothing here calls a model, and
nothing here decides pharmacology: the registry said "watch for swollen ankles", this file
says it in words he has. A dose change is rendered as a question for the doctor and never as
the new amount to take.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.drugs.registry import Interaction, Monograph
from app.errors import Refusal
from app.medicines import strings
from app.medicines.dose import Dose, Frequency
from app.medicines.models import ChangeKind


@dataclass(frozen=True, slots=True)
class Story:
    """One medicine, told in his words. Each section is a few whole sentences, one idea each;
    `lines` is the whole thing in order — the voice script. `generic` is the chemical name,
    for the small print, never in a sentence."""

    language: str
    name: str
    generic: str
    strength: str
    purpose: list[str]
    how_to_take: list[str]
    watch_out: list[str]
    avoid: list[str]
    if_forgotten: list[str]
    boundary: list[str]
    doctor_question: list[str] = field(default_factory=list)
    """Set only for a dose change: the same lines that open `how_to_take`, so a surface can
    show the question on its own card too."""

    @property
    def lines(self) -> list[str]:
        """The whole story in order — the voice script. The doctor question, when there is
        one, is already the first thing in `how_to_take`."""
        return [
            *self.purpose,
            *self.how_to_take,
            *self.watch_out,
            *self.avoid,
            *self.if_forgotten,
            *self.boundary,
        ]


STORY_PARTS: tuple[str, ...] = ("purpose", "how_to_take", "watch_out", "avoid", "if_forgotten")
"""The story as voice notes (E04-06): one note per part. The whole story runs near a minute
said at his pace, longer than one voice note may (`app.delivery.voice.MAX_SECONDS`)."""


class NothingToSay(Refusal):
    """This part of the story says nothing for this medicine, so it has no voice note."""


def voice_parts(story: Story) -> list[str]:
    """The parts of this story that say something, in the order they are told."""
    return [part for part in STORY_PARTS if getattr(story, part)]


def story_part(story: Story, part: str) -> tuple[list[str], str | None]:
    """One part of the story as it is said, and the boundary it ends on: the last part that
    says anything ends on the story's boundary lines, with the longer pause before them
    (`app.language.voice_script`). Pure, like the rest of the story."""
    parts = voice_parts(story)
    if part not in parts:
        raise NothingToSay(f"the story says nothing under {part!r}")
    lines = list(getattr(story, part))
    if part == parts[-1] and story.boundary:
        return [*lines, *story.boundary], "\n".join(story.boundary)
    return lines, None


def how_to_take(dose: Dose, monograph: Monograph, language: str) -> list[str]:
    """The dose as he would be told it: how much, how often, at which moments, with food or not.

    Anchors are the ones on the line or the defaults for the frequency, so a twice-a-day
    tablet is always "once with breakfast and once with dinner", never a bare "twice".
    """
    amount = strings.say_amount(dose.amount, dose.unit, language)
    slots = strings.anchor_slots([a.value for a in dose.scheduled_anchors], language)
    lines = strings.fill(strings.HOW_OFTEN[language][dose.frequency.value], amount=amount, **slots)
    if dose.frequency is not Frequency.PRN:
        lines.extend(strings.fill(strings.FOOD[language][monograph.food_rule_id]))
    return lines


def medication_story(
    *,
    generic: str,
    strength: str,
    dose: Dose,
    prescriber: str | None,
    change_kind: ChangeKind,
    monograph: Monograph,
    language: str | None,
) -> Story:
    """Render one medicine's story. Pure: rows in, sentences out, no model, no database."""
    lang = strings.language_of(language)
    name = strings.PLAIN_NAME[lang][monograph.plain_name_id]
    doctor = strings.say_doctor(prescriber, lang)
    words = {"name": name, "doctor": doctor}
    watch = [
        line
        for rule in monograph.watch_out_ids
        for line in strings.fill(strings.WATCH_OUT[lang][rule], **words)
    ]
    avoid = [
        line
        for rule in monograph.avoid_ids
        for line in strings.fill(strings.AVOID[lang][rule], **words)
    ]
    question = (
        strings.fill(strings.DOSE_CHANGE[lang], **words)
        if change_kind is ChangeKind.DOSE_CHANGE
        else []
    )
    # A dose change is not told as an amount. The amount lines are replaced by the question
    # for the doctor; the food rule still holds, whichever amount he settles on.
    taking = (
        how_to_take(dose, monograph, lang)
        if not question
        else [*question, *strings.fill(strings.FOOD[lang][monograph.food_rule_id])]
    )
    return Story(
        language=lang,
        name=name,
        generic=generic,
        strength=strength,
        purpose=strings.fill(strings.PURPOSE[lang][monograph.purpose_id], **words),
        how_to_take=taking,
        watch_out=watch,
        avoid=avoid,
        if_forgotten=strings.fill(
            strings.IF_FORGOTTEN[lang][monograph.missed_dose_rule_id], **words
        ),
        boundary=strings.fill(strings.BOUNDARY[lang], **words),
        doctor_question=question,
    )


def interaction_question(
    interaction: Interaction,
    *,
    names: dict[str, str],
    prescriber: str | None,
    language: str | None,
) -> list[str]:
    """One flagged pair as a question for the doctor, the two medicines named in his words.
    `names` maps each generic in the pair to its plain name (from the monographs)."""
    lang = strings.language_of(language)
    a, b = interaction.pair
    return strings.fill(
        strings.INTERACTION[lang][interaction.text_id],
        a=names.get(a, a),
        b=names.get(b, b),
        doctor=strings.say_doctor(prescriber, lang),
    )


def count_lines(
    *, name: str, remaining: float, unit: str, days: int | None, language: str | None
) -> list[str]:
    lang = strings.language_of(language)
    first, second = strings.COUNT[lang]
    lines = [first.format(amount=strings.say_amount(remaining, unit, lang), name=name)]
    if days is not None:
        lines.append(second.format(days=days))
    return lines


def reorder_lines(*, name: str, runs_out: date, language: str | None) -> list[str]:
    lang = strings.language_of(language)
    return strings.fill(strings.REORDER[lang], name=name, date=strings.say_date(runs_out, lang))


def dose_card_line(*, name: str, dose: Dose, anchor: str, language: str | None) -> str:
    lang = strings.language_of(language)
    return strings.DOSE_CARD[lang].format(
        amount=strings.say_amount(dose.amount, dose.unit, lang),
        name=name,
        anchor=strings.ANCHOR_WORDS[lang][anchor],
    )

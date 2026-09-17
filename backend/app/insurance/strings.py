"""The insurance module's own patient lines, in English, Malay and Chinese.

Every line here is tagged `@patient` and passes `app.safety.plain_words.verify` before it
leaves (`render`, the same contract as `app.channels.safety_strings.render`, kept as its own
small catalogue rather than added to that one — this module's lines are its own to change).

Two tiers of line, on purpose (the owner's decision, §`app.insurance.relevance`): a full-record
line names the insurer or says none is on file; a narrowed line says only to bring the card,
whatever the record holds, so a key that cannot see the record cannot learn from this line
whether one exists.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.errors import Refusal
from app.safety.plain_words import verify

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

NAME_SLOTS: frozenset[str] = frozenset({"name"})
NAME_STAND_IN = "Ash"


class NotPlainWords(Refusal):
    """A rendered line failed docs/plain-words.md. It does not reach him; the template is
    wrong."""

    def __init__(self, template_id: str, problems: list[str]) -> None:
        super().__init__(f"{template_id}: " + "; ".join(problems))
        self.template_id = template_id
        self.problems = problems


class NoSuchTemplate(Refusal):
    """A decision named a line this catalogue does not have."""


# @patient line
BRING_CARD: Mapping[str, str] = {
    "en": "Bring {name}'s insurance card to the visit.",
    "ms": "Bawa kad insurans {name} ke lawatan itu.",
    "zh": "带上{name}的保险卡去看诊。",
}
"""The one line a key that cannot see the money record gets, whatever it holds: it names no
insurer, no policy, no amount — only what to bring."""

# @patient line
HAS_COVER: Mapping[str, str] = {
    "en": "{name} has insurance on file.",
    "ms": "{name} ada insurans direkod.",
    "zh": "{name}有保险记录。",
}
"""Nura never says a visit *is* covered: this says cover is on file, on his own record —
paired with `MAY_APPLY` and `CONFIRM_WITH_INSURER`, which say it may apply and send him to
confirm it. One idea a line (plain-words review, #1): "on file" and "may apply" were one
sentence and are now two."""

# @patient line
MAY_APPLY: Mapping[str, str] = {
    "en": "It may apply to this visit.",
    "ms": "Ia mungkin berkaitan dengan lawatan ini.",
    "zh": "可能适用于这次看诊。",
}

# @patient line
CONFIRM_WITH_INSURER: Mapping[str, str] = {
    "en": "Confirm with the insurance company before the visit.",
    "ms": "Sahkan dengan syarikat insurans sebelum lawatan itu.",
    "zh": "看诊前请向保险公司确认。",
}
"""His words for the insurer, the same in every language (plain-words review, #2): "the
insurance company", not "the insurer" — the Malay and Chinese already said it this way."""

# @patient line
NO_COVER_ON_FILE: Mapping[str, str] = {
    "en": "Nura has no insurance on file for {name}.",
    "ms": "Nura tiada rekod insurans untuk {name}.",
    "zh": "Nura没有{name}的保险记录。",
}
"""The same words as `HAS_COVER` for the same idea (plain-words review, #13): "insurance on
file", not "insurance policy on file" — a fact on file is not a fact-of-a-different-name
depending on which line says it."""

# @patient line
CONFIRM_IF_ANY: Mapping[str, str] = {
    "en": "You can also confirm with the insurance company.",
    "ms": "Anda juga boleh sahkan dengan syarikat insurans itu.",
    "zh": "看诊前也可以向保险公司确认一下。",
}
"""Reframed from a conditional ("...if there is one.") that read as doubting the line just
said ("no insurance on file") to an offered extra step (plain-words review, #9)."""

# @patient line
BRING_POLICY_CARD: Mapping[str, str] = {
    "en": "Bring the insurance card to the visit.",
    "ms": "Bawa kad insurans itu ke lawatan itu.",
    "zh": "带上保险卡去看诊。",
}

# @patient line
BRING_GUARANTEE_LETTER: Mapping[str, str] = {
    "en": "Bring the insurance letter, if the insurer asks for one.",
    "ms": "Bawa surat insurans itu, jika syarikat insurans memintanya.",
    "zh": "如果保险公司要求，带上保险信。",
}
"""What the glossary calls a guarantee letter (docs/plain-words.md §4) is always said as
"the insurance letter" — the same words `Scope.MONEY` already uses for it
(`app.consent.texts.SCOPE_WORDS`)."""

TEMPLATES: Mapping[str, Mapping[str, str]] = {
    "insurance.bring_card": BRING_CARD,
    "insurance.has_cover": HAS_COVER,
    "insurance.may_apply": MAY_APPLY,
    "insurance.confirm_with_insurer": CONFIRM_WITH_INSURER,
    "insurance.no_cover_on_file": NO_COVER_ON_FILE,
    "insurance.confirm_if_any": CONFIRM_IF_ANY,
    "insurance.bring_policy_card": BRING_POLICY_CARD,
    "insurance.bring_guarantee_letter": BRING_GUARANTEE_LETTER,
}

def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def template(template_id: str, language: str) -> str:
    by_language = TEMPLATES.get(template_id)
    if by_language is None:
        raise NoSuchTemplate(f"no template {template_id}")
    return by_language.get(language_of(language)) or by_language[DEFAULT_LANGUAGE]


def render(template_id: str, language: str, **slots: str) -> str:
    """One line, filled and verified — the same contract as `app.channels.safety_strings.
    render`, kept small and local to this module."""
    lang = language_of(language)
    text = template(template_id, lang).format(**slots)
    checked = template(template_id, lang).format(
        **{k: NAME_STAND_IN if k in NAME_SLOTS else v for k, v in slots.items()}
    )
    failures = [
        f"rule {finding.rule} — {finding.problem}"
        for finding in verify(checked, lang, "line")
        if finding.severity == "fail"
    ]
    if failures:
        raise NotPlainWords(template_id, failures)
    return text


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGES",
    "NoSuchTemplate",
    "NotPlainWords",
    "render",
]

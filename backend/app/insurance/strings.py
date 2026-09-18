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
from app.regions import Region
from app.safety.plain_words import verify

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

NAME_SLOTS: frozenset[str] = frozenset({"name"})
NAME_STAND_IN = "Ash"

CURRENCY_BY_REGION: Mapping[Region, str] = {
    Region.SG: "S$",
    Region.MY: "RM",
}
"""His own currency symbol, from the region his profile is pinned to (`app.regions.Region`) —
never a symbol hard-coded at a call site (the ledger, `app.insurance.ledger`): a policy
carries no currency of its own, so the region is the one source of truth for it."""


def say_money(cents: int, region: Region) -> str:
    """An amount in minor units, in his own currency: 'S$420', 'S$420.50' — cents in, never a
    float, never a bare number with nothing to say what it is."""
    symbol = CURRENCY_BY_REGION[region]
    sign = "-" if cents < 0 else ""
    whole, remainder = divmod(abs(cents), 100)
    if remainder:
        return f"{sign}{symbol}{whole}.{remainder:02d}"
    return f"{sign}{symbol}{whole}"


# @patient phrase
CLAIM_STATUS_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "submitted": "filed",
        "in_review": "being checked",
        "approved": "approved",
        "partially_approved": "partly approved",
        "rejected": "not approved",
        "paid": "paid",
    },
    "ms": {
        "submitted": "difailkan",
        "in_review": "sedang disemak",
        "approved": "diluluskan",
        "partially_approved": "diluluskan sebahagian",
        "rejected": "tidak diluluskan",
        "paid": "telah dibayar",
    },
    "zh": {
        "submitted": "已提交",
        "in_review": "审核中",
        "approved": "已批准",
        "partially_approved": "部分批准",
        "rejected": "未批准",
        "paid": "已付款",
    },
}
"""The ledger's own word for a claim's status (`app.insurance.ledger`), short and plain — not
the enum value, which is never shown to him."""


def claim_status_word(status: str, language: str) -> str:
    lang = language_of(language)
    by_status = CLAIM_STATUS_WORDS.get(lang, CLAIM_STATUS_WORDS[DEFAULT_LANGUAGE])
    return by_status.get(status) or CLAIM_STATUS_WORDS[DEFAULT_LANGUAGE][status]


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

# @patient line
COST_TYPICAL_NOT_A_QUOTE: Mapping[str, str] = {
    "en": "This is a typical range, not a quote.",
    "ms": "Ini anggaran biasa, bukan sebut harga.",
    "zh": "这是一般范围，不是报价。",
}

# @patient line
COST_ASK_THE_CLINIC: Mapping[str, str] = {
    "en": "Ask what this visit will cost before he goes.",
    "ms": "Tanya berapa kos lawatan ini sebelum dia pergi.",
    "zh": "在他去看诊之前，先问清楚费用。",
}
"""Rule 13 (docs/plain-words.md §13) reserves "the clinic" for the doctor's own name; this
line names no place at all, only when to ask."""

# @patient line
COST_NO_BENCHMARK_FOUND: Mapping[str, str] = {
    "en": "Nura could not find a typical fee for this.",
    "ms": "Nura tidak menjumpai anggaran kos biasa untuk ini.",
    "zh": "Nura找不到这项的一般费用范围。",
}

# @patient line
COST_MAY_BE_COVERED: Mapping[str, str] = {
    "en": "{name}'s cover on file may pay part of this.",
    "ms": "Perlindungan insurans {name} yang direkod mungkin membayar sebahagiannya.",
    "zh": "{name}记录中的保险可能会支付部分费用。",
}

# @patient line
COST_NO_COVER_ON_FILE: Mapping[str, str] = {
    "en": "Nura has no insurance on file for {name} to check this against.",
    "ms": "Nura tiada rekod insurans untuk {name} bagi menyemak perkara ini.",
    "zh": "Nura没有{name}的保险记录可以用来核对这项费用。",
}

# @patient line
COST_COVER_NEEDS_MONEY_SCOPE: Mapping[str, str] = {
    "en": "Ask whoever manages {name}'s insurance letters what this may cost him.",
    "ms": "Tanya sesiapa yang menguruskan surat insurans {name} berapa kos ini mungkin baginya.",
    "zh": "请询问管理{name}保险信件的人，这可能要花多少钱。",
}
"""Named, never silent: the same words `Scope.MONEY` already carries
(`app.consent.texts.SCOPE_WORDS`, "insurance letters") for the one caller who cannot see the
covered part at all — a key without `Scope.MONEY` learns that it is withheld and who to ask,
never a blank field with no line about it."""

TEMPLATES: Mapping[str, Mapping[str, str]] = {
    "insurance.bring_card": BRING_CARD,
    "insurance.has_cover": HAS_COVER,
    "insurance.may_apply": MAY_APPLY,
    "insurance.confirm_with_insurer": CONFIRM_WITH_INSURER,
    "insurance.no_cover_on_file": NO_COVER_ON_FILE,
    "insurance.confirm_if_any": CONFIRM_IF_ANY,
    "insurance.bring_policy_card": BRING_POLICY_CARD,
    "insurance.bring_guarantee_letter": BRING_GUARANTEE_LETTER,
    "cost.typical_not_a_quote": COST_TYPICAL_NOT_A_QUOTE,
    "cost.ask_the_clinic": COST_ASK_THE_CLINIC,
    "cost.no_benchmark_found": COST_NO_BENCHMARK_FOUND,
    "cost.may_be_covered": COST_MAY_BE_COVERED,
    "cost.no_cover_on_file": COST_NO_COVER_ON_FILE,
    "cost.covered_needs_money_scope": COST_COVER_NEEDS_MONEY_SCOPE,
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

"""The red-flag table (`.claude/rules/safety.md`; docs/00-MASTER-BUILD-SPEC.md §10).

    Red flags (chest tightness, breathlessness at rest, one-sided swelling, worst-ever
    headache, sudden blurring, a fall, confusion, shaky-and-sweaty on sugar medicines, 1 kg
    or more in two days after a heart discharge) bypass planning and ranking: escalate
    immediately.

`RED_FLAGS` is that sentence as a table, one row per flag, with the words a person uses for
it in English, Malay and Chinese. `match_red_flags` reads a person's words against the table
and answers with the flags it heard — nothing more: no ranking, no severity, no sentence. A
flag is not a diagnosis. It is the one kind of thing Nura does not wait on, so the module
that hears it (`app.safety.not_feeling_well`) writes the flag down before anything else and
tells the family.

Two rows are conditional. `shaky_sweaty` is a flag only for someone on a sugar medicine; the
caller says whether he is, and when it cannot tell, the flag is *suppressed and named* so the
caregiver sees that it was (the rule "flags that depend on a missing fact are suppressed,
with the suppression visible"). `weight_gain_after_discharge` is read from the scales, not
from words, and has no words here; it is listed so the table is the whole rule.

Nothing here is model output. The words are a fixed list, and a word that is not in it is
not a flag — a person's words that match nothing go to the ordinary path, where the family
is still told.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class RedFlag(StrEnum):
    """The codes. The card and the notice name the flag by code; the words are the family's."""

    CHEST_PAIN = "chest_pain"
    BREATHLESS_AT_REST = "breathless_at_rest"
    ONE_SIDED_SWELLING = "one_sided_swelling"
    WORST_HEADACHE = "worst_headache"
    SUDDEN_BLURRING = "sudden_blurring"
    FALL = "fall"
    CONFUSION = "confusion"
    SHAKY_SWEATY = "shaky_sweaty"
    WEIGHT_GAIN_AFTER_DISCHARGE = "weight_gain_after_discharge"


@dataclass(frozen=True, slots=True)
class Rule:
    """One row of the table: the flag, the words for it, and what it depends on."""

    flag: RedFlag
    words: Mapping[str, tuple[str, ...]]
    """What a person says, by language code. Matched whole, case-insensitively."""
    needs_sugar_medicine: bool = False
    """True for the row that is a flag only for someone on a sugar medicine."""
    from_readings: bool = False
    """True for the row that is read from the scales, never from words."""


RED_FLAGS: tuple[Rule, ...] = (
    Rule(
        RedFlag.CHEST_PAIN,
        {
            "en": ("chest pain", "chest tightness", "chest tight", "tight chest", "chest hurts",
                   "pain in my chest", "pressure in my chest", "heart pain"),
            "ms": ("sakit dada", "dada ketat", "dada sakit", "dada saya sakit", "dada berat",
                   "dada tertekan"),
            "zh": ("胸痛", "胸口痛", "胸口闷", "胸闷", "胸口紧", "心口痛"),
        },
    ),
    Rule(
        RedFlag.BREATHLESS_AT_REST,
        {
            "en": ("cannot breathe", "can't breathe", "breathless", "short of breath",
                   "hard to breathe", "difficulty breathing", "gasping", "out of breath"),
            "ms": ("sesak nafas", "susah bernafas", "tak boleh bernafas", "semput", "termengah"),
            "zh": ("喘不过气", "呼吸困难", "透不过气", "气喘", "喘", "呼吸不了"),
        },
    ),
    Rule(
        RedFlag.ONE_SIDED_SWELLING,
        {
            "en": ("one leg swollen", "one leg is swollen", "one side swollen", "one arm swollen",
                   "left leg swollen", "right leg swollen", "one leg swelling",
                   "swollen on one side"),
            "ms": ("sebelah kaki bengkak", "kaki kiri bengkak", "kaki kanan bengkak",
                   "sebelah tangan bengkak", "bengkak sebelah"),
            "zh": ("一边腿肿", "一只腿肿", "左腿肿", "右腿肿", "一边手肿", "单边肿"),
        },
    ),
    Rule(
        RedFlag.WORST_HEADACHE,
        {
            "en": ("worst headache", "worst ever headache", "worst headache ever",
                   "headache like never before", "head is going to burst"),
            "ms": ("sakit kepala paling teruk", "sakit kepala teruk sangat",
                   "sakit kepala tak pernah macam ni"),
            "zh": ("最厉害的头痛", "从来没有这么痛的头", "头痛得要爆", "头要炸了"),
        },
    ),
    Rule(
        RedFlag.SUDDEN_BLURRING,
        {
            "en": ("suddenly blur", "sudden blur", "sudden blurring", "cannot see properly",
                   "suddenly cannot see", "vision blur", "eyes suddenly blur", "everything blur"),
            "ms": ("kabur tiba-tiba", "tiba-tiba kabur", "tiba-tiba tak nampak",
                   "mata kabur tiba-tiba", "pandangan kabur"),
            "zh": ("突然看不清", "突然模糊", "眼睛突然花", "突然看不见", "视线模糊"),
        },
    ),
    Rule(
        RedFlag.FALL,
        {
            "en": ("i fell", "fell down", "had a fall", "a fall", "fallen", "fell over",
                   "fell in the", "fell on the", "i fall"),
            "ms": ("jatuh", "terjatuh", "tergolek"),
            "zh": ("跌倒", "摔倒", "跌了", "摔了", "跌到"),
        },
    ),
    Rule(
        RedFlag.CONFUSION,
        {
            "en": ("confused", "confusion", "not making sense", "don't know where i am",
                   "do not know where i am", "mixed up", "cannot think straight"),
            "ms": ("keliru", "kebingungan", "tak tahu di mana", "mengelirukan", "nyanyuk tiba-tiba"),
            "zh": ("糊涂", "神志不清", "搞不清", "不知道在哪里", "迷糊", "胡言乱语"),
        },
    ),
    Rule(
        RedFlag.SHAKY_SWEATY,
        {
            "en": ("shaky and sweaty", "shaking and sweating", "shaky sweaty", "sweating and shaking",
                   "trembling and sweating", "cold sweat and shaking"),
            "ms": ("menggigil dan berpeluh", "gementar dan berpeluh", "berpeluh dan menggigil"),
            "zh": ("发抖出汗", "又抖又出汗", "手抖冒冷汗", "出冷汗发抖", "冒冷汗又发抖"),
        },
        needs_sugar_medicine=True,
    ),
    Rule(RedFlag.WEIGHT_GAIN_AFTER_DISCHARGE, {}, from_readings=True),
)

SUGAR_MEDICINE_CLASSES = frozenset({"biguanide", "sulfonylurea", "insulin", "dpp4_inhibitor",
                                    "sglt2_inhibitor", "meglitinide", "thiazolidinedione"})
"""The registry classes that make `shaky_sweaty` a flag. A product rule, not pharmacology:
whether a medicine is one of these is the licensed registry's word (`drug_class`)."""


@dataclass(frozen=True, slots=True)
class Heard:
    """What the table heard in a person's words: the flags, and the flags held back."""

    flags: tuple[RedFlag, ...]
    suppressed: tuple[RedFlag, ...]
    """Flags whose condition could not be checked — the person's medicines are not known —
    named so the caregiver sees the suppression, never quietly dropped."""

    @property
    def any(self) -> bool:
        return bool(self.flags)


def normalise(text: str) -> str:
    """Lower-cased, accents folded, one space between words, no punctuation to trip on."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = re.sub(r"[’‘`]", "'", folded)
    folded = re.sub(r"[^\w\s'一-鿿]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _says(words: str, phrase: str) -> bool:
    """Whether the phrase is in the words, whole. Chinese has no word boundaries, so a
    phrase in Chinese script is matched as a substring; anything else on word boundaries."""
    if re.search(r"[一-鿿]", phrase):
        return phrase in words
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", words) is not None


def match_red_flags(
    text: str,
    *,
    on_sugar_medicine: bool | None,
    languages: Iterable[str] = ("en", "ms", "zh"),
) -> Heard:
    """The flags in these words, in table order.

    Every language's words are tried whatever language the profile is set to: a Malay
    speaker says "chest pain" to his daughter in English, and the flag does not care.
    `on_sugar_medicine` is True or False when the medicines are known, None when they are
    not; the shaky-and-sweaty row is a flag only on True and is *suppressed and named* on
    None, so nothing about a missing fact is silent.
    """
    words = normalise(text)
    if not words:
        return Heard(flags=(), suppressed=())
    heard: list[RedFlag] = []
    suppressed: list[RedFlag] = []
    for rule in RED_FLAGS:
        if rule.from_readings:
            continue
        said = any(
            _says(words, normalise(phrase))
            for language in languages
            for phrase in rule.words.get(language, ())
        )
        if not said:
            continue
        if rule.needs_sugar_medicine:
            if on_sugar_medicine is None:
                suppressed.append(rule.flag)
                continue
            if not on_sugar_medicine:
                continue
        heard.append(rule.flag)
    return Heard(flags=tuple(heard), suppressed=tuple(suppressed))


def is_sugar_medicine(drug_class: str | None) -> bool:
    return drug_class is not None and drug_class.lower() in SUGAR_MEDICINE_CLASSES


def words_for(flag: RedFlag, language: str) -> str:
    """The first words of the table for a flag, in a language: what the notice quotes."""
    for rule in RED_FLAGS:
        if rule.flag is flag:
            options: Sequence[str] = rule.words.get(language) or rule.words.get("en") or ()
            return options[0] if options else flag.value.replace("_", " ")
    return flag.value.replace("_", " ")

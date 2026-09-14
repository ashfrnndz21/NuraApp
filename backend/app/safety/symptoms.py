"""How a person's words about how he feels become codes: the symptom, how much, since when.

A symptom is stored as a code from a fixed list, never as the words — the words stay in the
artefact (his voice note, or the text he typed, in the object store), which is where "logged
in his words" is kept true. Severity is one of three, in his words both ways: "a little"
(1), "quite a lot" (2), "very" (3). Duration is one of a few plain phrases. Anything the
tables do not know is left unset, never guessed: a symptom with no severity word has none.

This is parsing, not judgement. Nothing here says whether a symptom matters; the red flags
(`app.safety.red_flags`) are a separate table read first, and everything else is a pattern
for the doctor to hear about. The words a person says back (the log rendered in plain
words) live in `app.channels.safety_strings`, under the verifier.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


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


class Symptom(StrEnum):
    """The fixed list. A word that maps to none of these is kept only in the artefact."""

    TIRED = "tired"
    DIZZY = "dizzy"
    HEADACHE = "headache"
    NAUSEA = "nausea"
    VOMITING = "vomiting"
    COUGH = "cough"
    FEVER = "fever"
    STOMACH_PAIN = "stomach_pain"
    POOR_APPETITE = "poor_appetite"
    CANNOT_SLEEP = "cannot_sleep"
    LEG_SWELLING = "leg_swelling"
    WEAK = "weak"
    JOINT_PAIN = "joint_pain"
    DIARRHOEA = "diarrhoea"
    CONSTIPATION = "constipation"
    ITCH = "itch"
    NOT_WELL = "not_well"
    """He said he is not feeling well and named nothing the list knows."""


SYMPTOM_WORDS: Mapping[Symptom, Mapping[str, tuple[str, ...]]] = {
    Symptom.TIRED: {
        "en": ("tired", "no energy", "exhausted", "weary", "lethargic", "sleepy all day"),
        "ms": ("letih", "penat", "tak bertenaga", "lesu"),
        "zh": ("累", "疲倦", "没力气", "没精神", "很疲劳"),
    },
    Symptom.DIZZY: {
        "en": ("dizzy", "giddy", "light headed", "lightheaded", "head spinning", "spinning"),
        "ms": ("pening", "pusing", "kepala pusing", "berpinar"),
        "zh": ("头晕", "晕", "眩晕", "天旋地转"),
    },
    Symptom.HEADACHE: {
        "en": ("headache", "head hurts", "head pain", "my head is painful"),
        "ms": ("sakit kepala", "kepala sakit"),
        "zh": ("头痛", "头疼"),
    },
    Symptom.NAUSEA: {
        "en": ("nausea", "nauseous", "feel like vomiting", "feel sick", "queasy"),
        "ms": ("loya", "rasa nak muntah", "mual"),
        "zh": ("恶心", "想吐", "反胃"),
    },
    Symptom.VOMITING: {
        "en": ("vomit", "vomited", "vomiting", "threw up", "throwing up"),
        "ms": ("muntah", "termuntah"),
        "zh": ("吐了", "呕吐", "呕"),
    },
    Symptom.COUGH: {
        "en": ("cough", "coughing"),
        "ms": ("batuk",),
        "zh": ("咳嗽", "咳"),
    },
    Symptom.FEVER: {
        "en": ("fever", "feverish", "hot and cold", "chills", "temperature"),
        "ms": ("demam", "panas badan", "seram sejuk"),
        "zh": ("发烧", "发热", "发冷"),
    },
    Symptom.STOMACH_PAIN: {
        "en": ("stomach pain", "stomach ache", "stomachache", "tummy pain", "belly pain",
               "stomach hurts", "abdominal pain"),
        "ms": ("sakit perut", "perut sakit", "perut memulas"),
        "zh": ("肚子痛", "胃痛", "腹痛", "肚子疼"),
    },
    Symptom.POOR_APPETITE: {
        "en": ("no appetite", "not hungry", "cannot eat", "don't feel like eating",
               "do not feel like eating", "poor appetite"),
        "ms": ("tak selera", "tak lalu makan", "tiada selera"),
        "zh": ("没胃口", "不想吃", "吃不下"),
    },
    Symptom.CANNOT_SLEEP: {
        "en": ("cannot sleep", "can't sleep", "could not sleep", "couldn't sleep", "no sleep",
               "insomnia", "did not sleep"),
        "ms": ("tak boleh tidur", "susah tidur", "tak dapat tidur"),
        "zh": ("睡不着", "失眠", "睡不好"),
    },
    Symptom.LEG_SWELLING: {
        "en": ("legs swollen", "swollen legs", "legs are swollen", "both legs swollen",
               "feet swollen", "swollen feet", "ankles swollen", "legs swelling"),
        "ms": ("kaki bengkak", "kedua kaki bengkak", "bengkak kaki"),
        "zh": ("腿肿", "脚肿", "两腿都肿", "脚肿了"),
    },
    Symptom.WEAK: {
        "en": ("weak", "weakness", "no strength", "legs weak", "feel faint", "wobbly"),
        "ms": ("lemah", "tak berdaya", "kaki lemah", "rasa nak pitam"),
        "zh": ("无力", "虚弱", "腿软", "要昏倒"),
    },
    Symptom.JOINT_PAIN: {
        "en": ("knee pain", "joint pain", "knees hurt", "joints hurt", "back pain", "backache"),
        "ms": ("sakit lutut", "sakit sendi", "sakit pinggang", "sakit belakang"),
        "zh": ("膝盖痛", "关节痛", "腰痛", "背痛"),
    },
    Symptom.DIARRHOEA: {
        "en": ("diarrhoea", "diarrhea", "loose stool", "loose stools", "runny stomach"),
        "ms": ("cirit", "cirit birit", "cirit-birit"),
        "zh": ("拉肚子", "腹泻"),
    },
    Symptom.CONSTIPATION: {
        "en": ("constipated", "constipation", "cannot pass motion", "can't pass motion"),
        "ms": ("sembelit", "susah buang air besar"),
        "zh": ("便秘", "大便不通"),
    },
    Symptom.ITCH: {
        "en": ("itchy", "itch", "itching", "rash"),
        "ms": ("gatal", "ruam"),
        "zh": ("痒", "发痒", "起疹"),
    },
}
"""What a person says for each symptom, by language. The list is fixed and small on purpose:
his words for the rest stay in the artefact and reach the doctor as his words."""


SEVERITY_WORDS: Mapping[int, Mapping[str, tuple[str, ...]]] = {
    1: {
        "en": ("only a little", "a little", "a bit", "slightly", "a little bit", "mild", "not much"),
        "ms": ("sedikit saja", "sedikit", "sikit", "sikit-sikit", "sikit saja"),
        "zh": ("只有一点", "一点", "一点点", "有点", "稍微", "轻微"),
    },
    2: {
        "en": ("quite bad", "quite a lot", "a lot", "moderate", "quite", "rather"),
        "ms": ("agak teruk", "agak banyak", "banyak", "sederhana", "agak"),
        "zh": ("比较严重", "比较多", "比较", "相当", "挺", "蛮", "不少"),
    },
    3: {
        "en": ("very bad", "very", "really bad", "severe", "terrible", "so much", "extremely"),
        "ms": ("teruk sangat", "sangat", "amat", "sangat teruk", "parah"),
        "zh": ("很严重", "很", "非常", "厉害", "严重", "太"),
    },
}
"""How much, in three steps, in his words. The first entry per language is the one said back
— the same words the catalogue (`app.channels.safety_strings.SEVERITY_WORDS`) shows and
speaks, so there is one vocabulary for three levels, checked by a test."""


class Duration(StrEnum):
    """Since when, as a person says it."""

    JUST_NOW = "just_now"
    THIS_MORNING = "this_morning"
    SINCE_YESTERDAY = "since_yesterday"
    FEW_DAYS = "few_days"
    ABOUT_A_WEEK = "about_a_week"
    LONGER = "longer"


DURATION_WORDS: Mapping[Duration, Mapping[str, tuple[str, ...]]] = {
    Duration.JUST_NOW: {
        "en": ("just now", "right now", "suddenly", "a moment ago", "just started"),
        "ms": ("tadi", "baru tadi", "sekarang", "tiba-tiba", "baru mula"),
        "zh": ("刚刚", "刚才", "现在", "突然", "刚开始"),
    },
    Duration.THIS_MORNING: {
        "en": ("since this morning", "this morning", "since morning", "from this morning",
               "since i woke up", "today"),
        "ms": ("sejak pagi", "pagi tadi", "dari pagi", "hari ini"),
        "zh": ("今天早上", "从早上", "早上开始", "今天"),
    },
    Duration.SINCE_YESTERDAY: {
        "en": ("since yesterday", "yesterday", "from yesterday", "last night", "since last night"),
        "ms": ("sejak semalam", "semalam", "dari semalam", "malam tadi"),
        "zh": ("昨天", "从昨天", "昨晚", "昨天开始"),
    },
    Duration.FEW_DAYS: {
        "en": ("few days", "a few days", "2 days", "two days", "3 days", "three days",
               "for days", "several days", "4 days", "5 days"),
        "ms": ("beberapa hari", "2 hari", "dua hari", "3 hari", "tiga hari", "dah berhari"),
        "zh": ("几天", "两天", "三天", "好几天", "2天", "3天"),
    },
    Duration.ABOUT_A_WEEK: {
        "en": ("a week", "one week", "about a week", "since last week", "for a week",
               "whole week"),
        "ms": ("seminggu", "satu minggu", "sejak minggu lepas", "dah seminggu"),
        "zh": ("一个星期", "一周", "上个星期", "一星期"),
    },
    Duration.LONGER: {
        "en": ("weeks", "for weeks", "a month", "months", "long time", "a long time",
               "since last month"),
        "ms": ("berminggu", "sebulan", "berbulan", "dah lama", "lama dah"),
        "zh": ("几个星期", "一个月", "几个月", "很久", "好久"),
    },
}


@dataclass(frozen=True, slots=True)
class Parsed:
    """What the tables read in a person's words. Unset where they read nothing."""

    symptoms: tuple[Symptom, ...]
    severity: int | None
    duration: Duration | None

    @property
    def heard_anything(self) -> bool:
        return bool(self.symptoms) or self.severity is not None or self.duration is not None


def _first_match[Code](
    words: str, table: Mapping[Code, Mapping[str, tuple[str, ...]]]
) -> list[Code]:
    found: list[Code] = []
    for code, by_language in table.items():
        if any(
            _says(words, normalise(phrase))
            for phrases in by_language.values()
            for phrase in phrases
        ):
            found.append(code)
    return found


def parse_symptoms(text: str) -> Parsed:
    """Read the symptoms, the severity and the duration in a person's words, in every
    language at once: a Hokkien speaker mixes three in one breath.

    Severity takes the strongest word said, so "very tired, a bit dizzy" is 3: what matters
    for the doctor is the worst of it, and the words themselves are in the artefact.
    """
    words = normalise(text)
    if not words:
        return Parsed(symptoms=(), severity=None, duration=None)
    symptoms = tuple(_first_match(words, SYMPTOM_WORDS))
    levels = _first_match(words, SEVERITY_WORDS)
    durations = _first_match(words, DURATION_WORDS)
    return Parsed(
        symptoms=symptoms,
        severity=max(levels) if levels else None,
        duration=durations[0] if durations else None,
    )


def severity_word(level: int, language: str) -> str:
    """The plain word for a level, the first the table lists: the same words every time."""
    by_language = SEVERITY_WORDS[level]
    return (by_language.get(language) or by_language["en"])[0]


def severity_level(word: str) -> int | None:
    """The level for a plain word, or None: the other direction of `severity_word`."""
    said = normalise(word)
    for level, by_language in SEVERITY_WORDS.items():
        if any(normalise(phrase) == said for phrases in by_language.values() for phrase in phrases):
            return level
    return None

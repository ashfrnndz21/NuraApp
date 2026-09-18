"""The words of the visit loop: every line a patient reads on a brief, a questions card, a
post-visit summary or a memo, as a template, in English, Malay and Chinese.

Nothing rendered for him is assembled at run time from pieces: each line is one whole
template with `{slots}` for a name, a date, a time or a number, tagged `@patient` (or
`@patient action` for a line that tells him to do something, which must also say when and
who) so that `make plain-words` reads it with the right rules, and the rendered line is
checked again by `app.safety.plain_words.verify` before it is stored (`verified`). A line
that fails is refused (`NotPlainEnough`) and never shown. Every slot value is checked
against a rule for that slot before it is rendered (`SLOT_RULES`): a name is a name, a
number is a number, and nothing free ever reaches a line. The sentence for a medicine change
is a question for the doctor, never the change: the model that read the transcript
classifies, and the template speaks. Every printed line has a spoken twin (`spoken`): the
chemical name in brackets is a print device and is not read aloud.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.db import as_utc
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.errors import Refusal
from app.medicines.strings import PLAIN_NAME
from app.regions import REGION_TZ, Region
from app.safety.plain_words import Kind, verify

LANGUAGES: tuple[str, ...] = ("en", "ms", "zh")
"""The languages the visit loop speaks. A profile in any other language is spoken to in
English until its words are here — the fallback is a stated decision, never a guess."""

FALLBACK_LANGUAGE = "en"


class NotPlainEnough(Refusal):
    """A line for the patient failed the plain-words verifier, and was not shown."""

    def __init__(self, text: str, problems: list[str]) -> None:
        super().__init__(f"not plain enough: {'; '.join(problems)}")
        self.text = text
        self.problems = problems


class NoSuchTemplate(Refusal):
    """The visit loop renders only from its own templates. This key is not one."""


class NotASlotValue(Refusal):
    """A value offered for a slot was not the kind of thing the slot takes: a name with
    digits in it, a number that is not a number, a line where a word should be."""


def language_for(code: str | None) -> str:
    """The language the loop speaks to this profile in."""
    return code if code in LANGUAGES else FALLBACK_LANGUAGE


# --- the day, the date and the time --------------------------------------------------------

WEEKDAYS: Mapping[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ms": ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
}
MONTHS: Mapping[str, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "ms": (
        "Januari",
        "Februari",
        "Mac",
        "April",
        "Mei",
        "Jun",
        "Julai",
        "Ogos",
        "September",
        "Oktober",
        "November",
        "Disember",
    ),
}


def day_and_date(moment: datetime, language: str, region: Region) -> str:
    """Rule 5: "Monday 29 September" — in Chinese the date and then the day, "9月29日星期一" —
    on the patient's own clock, in his language."""
    local = as_utc(moment).astimezone(REGION_TZ[region])
    lang = language_for(language)
    weekday = WEEKDAYS[lang][local.weekday()]
    if lang == "zh":
        return f"{local.month}月{local.day}日{weekday}"
    return f"{weekday} {local.day} {MONTHS[lang][local.month - 1]}"


# @patient phrase
_PERIODS: Mapping[str, tuple[tuple[int, str], ...]] = {
    "en": ((5, "in the morning"), (12, "noon"), (13, "in the afternoon"), (18, "in the evening")),
    "ms": ((5, "pagi"), (12, "tengah hari"), (14, "petang"), (19, "malam")),
    "zh": ((5, "上午"), (12, "中午"), (13, "下午"), (18, "晚上")),
}
"""How he says which part of the day an hour is in, by the hour it starts."""


def _period(hour: int, language: str) -> str:
    table = _PERIODS[language]
    chosen = table[-1][1]  # before the first boundary is still the night
    for starts, words in table:
        if hour >= starts:
            chosen = words
    return chosen


def time_of_day(moment: datetime, language: str, region: Region) -> str:
    """Rule 5: "10 in the morning", never "10:00" — on his clock, in his language."""
    local = as_utc(moment).astimezone(REGION_TZ[region])
    lang = language_for(language)
    hour12 = local.hour % 12 or 12
    period = _period(local.hour, lang)
    if lang == "zh":
        if local.minute == 0:
            return f"{period}{hour12}点"
        if local.minute == 30:
            return f"{period}{hour12}点半"
        return f"{period}{hour12}点{local.minute}分"
    if local.minute == 0:
        return f"{hour12} {period}"
    if lang == "en" and local.minute == 30:
        return f"half past {hour12} {period}"
    return f"{hour12}.{local.minute:02d} {period}"


# --- his words for things ------------------------------------------------------------------

# @patient phrase
SUBJECT_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood_pressure": "your blood pressure",
        "blood_sugar": "your sugar test",
        "weight": "your weight",
        "heart_rate": "your pulse",
        "lipid_panel": "your cholesterol test",
        "kidney": "your kidney test",
        "medicine": "your medicines",
        "medication": "your medicines",
        "symptom": "how you feel",
        "hypertension": "your blood pressure",
        "diabetes": "your sugar",
    },
    "ms": {
        "blood_pressure": "tekanan darah anda",
        "blood_sugar": "ujian gula anda",
        "weight": "berat badan anda",
        "heart_rate": "nadi anda",
        "lipid_panel": "ujian kolesterol anda",
        "kidney": "ujian buah pinggang anda",
        "medicine": "ubat anda",
        "medication": "ubat anda",
        "symptom": "apa yang anda rasa",
        "hypertension": "tekanan darah anda",
        "diabetes": "gula anda",
    },
    "zh": {
        "blood_pressure": "您的血压",
        "blood_sugar": "您的血糖检查",
        "weight": "您的体重",
        "heart_rate": "您的脉搏",
        "lipid_panel": "您的胆固醇检查",
        "kidney": "您的肾检查",
        "medicine": "您的药",
        "medication": "您的药",
        "symptom": "您的感觉",
        "hypertension": "您的血压",
        "diabetes": "您的血糖",
    },
}
"""A subject code, in his words. A code not here has no words: the loop says a whole
fallback line instead ("Tell {doctor} about how you feel today."), never the code."""

# @patient phrase
VISIT_SUBJECTS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood_pressure": "your blood pressure",
        "sugar": "your sugar",
        "kidneys": "your kidneys",
        "heart": "your heart",
        "eyes": "your eyes",
        "cholesterol": "your cholesterol",
        "medicines": "your medicines",
        "blood_test": "your blood test",
        "general_check": "your health check",
    },
    "ms": {
        "blood_pressure": "tekanan darah anda",
        "sugar": "gula anda",
        "kidneys": "buah pinggang anda",
        "heart": "jantung anda",
        "eyes": "mata anda",
        "cholesterol": "kolesterol anda",
        "medicines": "ubat anda",
        "blood_test": "ujian darah anda",
        "general_check": "pemeriksaan kesihatan anda",
    },
    "zh": {
        "blood_pressure": "您的血压",
        "sugar": "您的血糖",
        "kidneys": "您的肾",
        "heart": "您的心脏",
        "eyes": "您的眼睛",
        "cholesterol": "您的胆固醇",
        "medicines": "您的药",
        "blood_test": "您的验血",
        "general_check": "您的健康检查",
    },
}
"""What a visit can be about, as a fixed code with his words in each language. A booking's
purpose label is a caregiver's free text and never reaches him: `purpose_code` maps it
here, and a label that maps to nothing is "your health"."""

_PURPOSE_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "blood_pressure",
        re.compile(r"blood pressure|tekanan darah|\bbp\b|hypertens|darah tinggi|血压"),
    ),
    ("sugar", re.compile(r"sugar|diabet|\bgula\b|kencing manis|glucose|hba1c|血糖|糖尿")),
    ("kidneys", re.compile(r"kidney|renal|buah pinggang|\bginjal\b|肾")),
    ("heart", re.compile(r"\bheart\b|cardio|cardiac|jantung|心脏|心臟")),
    ("eyes", re.compile(r"\beyes?\b|\bmata\b|retina|眼")),
    ("cholesterol", re.compile(r"cholesterol|kolesterol|lipid|胆固醇")),
    ("blood_test", re.compile(r"blood test|ujian darah|\blabs?\b|验血|抽血")),
    ("medicines", re.compile(r"medicin|medication|\bubat\b|prescription|药")),
    ("general_check", re.compile(r"check|review|follow|pemeriksaan|susulan|检查|复诊")),
)


def purpose_code(label: str | None) -> str | None:
    """The fixed visit subject a booking's purpose label names, or None when it names none."""
    if not label:
        return None
    lowered = label.strip().lower()
    for code, pattern in _PURPOSE_KEYWORDS:
        if pattern.search(lowered):
            return code
    return None


def visit_subject_words(code: str, language: str) -> str:
    return VISIT_SUBJECTS[language_for(language)][code]


# @patient phrase
YOUR_HEALTH: Mapping[str, str] = {"en": "your health", "ms": "kesihatan anda", "zh": "您的健康"}
"""What a visit is about when its booking names no subject: the brief's T-3 message says "This
visit is about your health." (`visit_about_health` on the brief itself)."""


# @patient phrase
MEDICINE_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "furosemide": "the water pill",
        "frusemide": "the water pill",
        "amlodipine": "your blood pressure tablet",
        "atorvastatin": "the cholesterol tablet",
        "metformin": "the sugar tablet",
    },
    "ms": {
        "furosemide": "pil air",
        "frusemide": "pil air",
        "amlodipine": "ubat tekanan darah anda",
        "atorvastatin": "ubat kolesterol",
        "metformin": "ubat gula",
    },
    "zh": {
        "furosemide": "去水药",
        "frusemide": "去水药",
        "amlodipine": "您的血压药",
        "atorvastatin": "降胆固醇药",
        "metformin": "降糖药",
    },
}
"""The glossary of docs/plain-words.md as a table, in the same words the medicines module
uses (`app.medicines.strings.PLAIN_NAME`), so one medicine has one name on every card: his
name first, the chemical name second and small. Used when the licensed register has no
monograph for a generic; the monograph's plain name comes first."""

# @patient phrase
RED_FLAG_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "chest_pain": "the chest pain",
        "breathless": "the trouble breathing",
        "black_stool": "the black stool",
        "fall": "the fall",
        "confusion": "the muddled feeling",
        "one_sided_swelling": "the swollen leg",
        "worst_headache": "the bad headache",
        "sudden_blurring": "the blurry eyes",
        "shaky_and_sweaty": "feeling shaky and sweaty",
        "fever_on_medicine": "the fever",
    },
    "ms": {
        "chest_pain": "sakit dada",
        "breathless": "sesak nafas",
        "black_stool": "najis hitam",
        "fall": "jatuh",
        "confusion": "keliru",
        "one_sided_swelling": "kaki bengkak",
        "worst_headache": "sakit kepala teruk",
        "sudden_blurring": "mata kabur",
        "shaky_and_sweaty": "menggigil dan berpeluh",
        "fever_on_medicine": "demam",
    },
    "zh": {
        "chest_pain": "胸痛",
        "breathless": "喘不过气",
        "black_stool": "大便发黑",
        "fall": "跌倒",
        "confusion": "糊涂",
        "one_sided_swelling": "腿肿",
        "worst_headache": "很厉害的头痛",
        "sudden_blurring": "眼睛模糊",
        "shaky_and_sweaty": "发抖又出汗",
        "fever_on_medicine": "发烧",
    },
}


def subject_words(subject: str, language: str) -> str:
    """His words for a subject code, or `NotASlotValue`: a code the table does not know is
    never turned into patient text at run time (a line is never assembled from a code)."""
    lang = language_for(language)
    words = SUBJECT_WORDS[lang].get(subject)
    if words is None:
        raise NotASlotValue(f"no words for subject {subject!r}")
    return words


def has_subject_words(subject: str) -> bool:
    return subject in SUBJECT_WORDS["en"]


def medicine_words(name: str, language: str, registry: DrugRegistry | None = None) -> str:
    """His name for the medicine first — the licensed monograph's plain name (E04,
    `app.medicines.strings.PLAIN_NAME`) when the registry knows the generic, the glossary's
    otherwise — with the generic second in brackets in English; in Malay and Chinese his name
    alone, because the verifier's glossary knows the chemical name and only the English word
    beside it. A medicine neither knows is not named here at all: the caller has already
    checked the generic against the register (`summary.known_generic`) and says "your
    medicines" for one it does not know, so nothing unregistered reaches a line."""
    lang = language_for(language)
    generic = name.strip().lower()
    plain: str | None = None
    if registry is not None:
        try:
            plain = PLAIN_NAME[lang][registry.monograph(generic).plain_name_id]
        except (UnknownDrug, KeyError):
            plain = None
    if plain is None:
        plain = MEDICINE_WORDS[lang].get(generic)
    if plain is None:
        raise NotASlotValue(f"no plain name for {generic!r}: the register does not know it")
    if lang != "en" or generic in plain.lower():
        return plain
    return f"{plain} ({generic})"


def red_flag_words(code: str, language: str) -> str:
    lang = language_for(language)
    words = RED_FLAG_WORDS[lang].get(code)
    if words is None:
        raise NotASlotValue(f"no words for red flag {code!r}")
    return words


_BRACKETED = re.compile(r"\s*\([^()]*\)")


def spoken(text: str) -> str:
    """The spoken twin of a printed line: the chemical name in brackets is not read aloud."""
    return _BRACKETED.sub("", text)


# --- the templates -------------------------------------------------------------------------

# @patient
LINE_TEMPLATES: Mapping[str, Mapping[str, str]] = {
    # The brief.
    "visit_with": {
        "en": "You see {doctor} on {day} at {time}.",
        "ms": "Anda berjumpa {doctor} pada {day} pukul {time}.",
        "zh": "您在{day}{time}看{doctor}。",
    },
    "visit_about": {
        "en": "This visit is about {subject}.",
        "ms": "Lawatan ini untuk memeriksa {subject}.",
        "zh": "这次看医生是为了{subject}。",
    },
    "visit_about_health": {
        "en": "This visit is about your health.",
        "ms": "Lawatan ini untuk kesihatan anda.",
        "zh": "这次看医生是为了您的健康。",
    },
    "changed_readings_one": {
        "en": "Since {day}, 1 new number is in your blood pressure book.",
        "ms": "Sejak {day}, ada 1 nombor baru dalam buku tekanan darah anda.",
        "zh": "自{day}以来，您的血压本多了1个新数字。",
    },
    "changed_medicines_one": {
        "en": "Since {day}, 1 thing changed about your medicines.",
        "ms": "Sejak {day}, 1 perkara berubah tentang ubat anda.",
        "zh": "自{day}以来，您的药有1处变化。",
    },
    "changed_papers_one": {
        "en": "Since {day}, 1 new thing is in your papers.",
        "ms": "Sejak {day}, ada 1 perkara baru dalam surat-surat anda.",
        "zh": "自{day}以来，您的病历文件多了1项新内容。",
    },
    "changed_how_you_are_one": {
        "en": "Since {day}, 1 thing changed about how you feel.",
        "ms": "Sejak {day}, 1 perkara berubah tentang apa yang anda rasa.",
        "zh": "自{day}以来，您的感觉有1处变化。",
    },
    "changed_readings": {
        "en": "Since {day}, {count} new numbers are in your blood pressure book.",
        "ms": "Sejak {day}, ada {count} nombor baru dalam buku tekanan darah anda.",
        "zh": "自{day}以来，您的血压本多了{count}个新数字。",
    },
    "changed_medicines": {
        "en": "Since {day}, {count} things changed about your medicines.",
        "ms": "Sejak {day}, {count} perkara berubah tentang ubat anda.",
        "zh": "自{day}以来，您的药有{count}处变化。",
    },
    "changed_papers": {
        "en": "Since {day}, {count} new things are in your papers.",
        "ms": "Sejak {day}, ada {count} perkara baru dalam surat-surat anda.",
        "zh": "自{day}以来，您的病历文件多了{count}项新内容。",
    },
    "changed_how_you_are": {
        "en": "Since {day}, {count} things changed about how you feel.",
        "ms": "Sejak {day}, {count} perkara berubah tentang apa yang anda rasa.",
        "zh": "自{day}以来，您的感觉有{count}处变化。",
    },
    "nothing_changed": {
        "en": "Nothing has changed since {day}.",
        "ms": "Tiada apa yang berubah sejak {day}.",
        "zh": "自{day}以来没有变化。",
    },
    # What does not fit on the one page (E05-01), said as a count.
    "symptoms_more": {
        "en": "Nura has more notes about how you feel.",
        "ms": "Nura ada lagi nota tentang apa yang anda rasa.",
        "zh": "Nura还记下了更多您的感觉。",
    },
    "questions_more": {
        "en": "Nura has {count} more questions for {doctor}.",
        "ms": "Nura ada {count} lagi soalan untuk {doctor}.",
        "zh": "Nura还有{count}个问题要问{doctor}。",
    },
    "bring_more": {
        "en": "Nura has {count} more things for you to bring on {day}.",
        "ms": "Nura ada {count} lagi barang untuk anda bawa pada {day}.",
        "zh": "Nura还有{count}样东西要您在{day}带去。",
    },
    # Questions, from gaps.
    "ask_fact_expired": {
        "en": "Ask {doctor} about {thing} again.",
        "ms": "Tanya {doctor} tentang {thing} sekali lagi.",
        "zh": "再问一问{doctor}，{thing}怎么样。",
    },
    "ask_reading_stale": {
        "en": "Ask {doctor} how often to take your blood pressure.",
        "ms": "Tanya {doctor} berapa kerap perlu ambil tekanan darah.",
        "zh": "问{doctor}您应该多久量一次血压。",
    },
    "ask_medicine_purpose": {
        "en": "Ask {doctor} what {medicine} is for.",
        "ms": "Tanya {doctor} untuk apa {medicine}.",
        "zh": "问{doctor}{medicine}是治什么的。",
    },
    "ask_interaction": {
        "en": "Ask {doctor} if {medicine} and {other} are OK together.",
        "ms": "Tanya {doctor} sama ada {medicine} dan {other} boleh dimakan bersama.",
        "zh": "问{doctor}{medicine}和{other}一起吃行不行。",
    },
    "tell_dispute": {
        "en": "Tell {doctor} that your papers do not agree about {thing}.",
        "ms": "Beritahu {doctor} yang surat-surat anda tidak sama tentang {thing}.",
        "zh": "告诉{doctor}，您的病历文件上{thing}写得不一样。",
    },
    "ask_visit_purpose": {
        "en": "Ask {doctor} what this visit is for.",
        "ms": "Tanya {doctor} untuk apa lawatan ini.",
        "zh": "问{doctor}这次看诊是为了什么。",
    },
    # Questions and memos, from a medicine change heard. A question for the doctor, never
    # the change itself, and never an amount.
    "ask_new_amount": {
        "en": "Ask {doctor} about the new amount of {medicine}.",
        "ms": "Tanya {doctor} tentang jumlah baru {medicine}.",
        "zh": "问{doctor}，{medicine}现在要吃多少。",
    },
    "ask_starting": {
        "en": "Ask {doctor} about starting {medicine}.",
        "ms": "Tanya {doctor} tentang mula makan {medicine}.",
        "zh": "问一问{doctor}，{medicine}要不要开始吃。",
    },
    "ask_stopping": {
        "en": "Ask {doctor} about stopping {medicine}.",
        "ms": "Tanya {doctor} tentang berhenti makan {medicine}.",
        "zh": "问一问{doctor}，{medicine}要不要停。",
    },
    "ask_medicine_change": {
        "en": "Ask {doctor} about the change to {medicine}.",
        "ms": "Tanya {doctor} tentang perubahan pada {medicine}.",
        "zh": "问一问{doctor}，{medicine}有什么变化。",
    },
    # A question from a safety notice a search job found (#181/#224): its own words are never
    # kept, only that there is a notice to ask about.
    "ask_safety_notice": {
        "en": "Ask {doctor} about the notice on {medicine}.",
        "ms": "Tanya {doctor} tentang notis pada {medicine}.",
        "zh": "问一问{doctor}，关于{medicine}的通知。",
    },
    "ask_medicines_change": {
        "en": "Ask {doctor} about the change to your medicines.",
        "ms": "Tanya {doctor} tentang perubahan pada ubat anda.",
        "zh": "问一问{doctor}，您的药有什么变化。",
    },
    # The questions card for him.
    "no_need_to_remember": {
        "en": "Nura keeps these questions for you.",
        "ms": "Nura simpan soalan-soalan ini untuk anda.",
        "zh": "这些问题Nura帮您记着。",
    },
    # The summary.
    "doctor_said_on": {
        "en": "{doctor} said this on {day}.",
        "ms": "{doctor} berkata begini pada {day}.",
        "zh": "{doctor}在{day}说了这些。",
    },
    "see_again_on": {
        "en": "You see {doctor} again on {day} at {time}.",
        "ms": "Anda berjumpa {doctor} lagi pada {day} pukul {time}.",
        "zh": "您在{day}{time}再看{doctor}。",
    },
    "will_book_it": {
        "en": "{who} will book it.",
        "ms": "{who} akan tempahkannya.",
        "zh": "{who}会去预约。",
    },
    "tell_doctor_how_you_feel": {
        "en": "Tell {doctor} about how you feel today.",
        "ms": "Beritahu {doctor} tentang apa yang anda rasa hari ini.",
        "zh": "今天就告诉{doctor}您的感觉。",
    },
    "doctor_wrote_down": {
        "en": "{doctor} wrote down {thing}.",
        "ms": "{doctor} mencatat {thing}.",
        "zh": "{doctor}记下了{thing}。",
    },
    "medicines_unchanged_said": {
        "en": "{doctor} said your medicines stay the same.",
        "ms": "{doctor} kata ubat anda kekal sama.",
        "zh": "{doctor}说您的药不变。",
    },
    "water_is_ok": {
        "en": "Water is OK.",
        "ms": "Air kosong boleh.",
        "zh": "喝水没问题。",
    },
    "blood_test_on": {
        "en": "You have a blood test on {day}.",
        "ms": "Anda ada ujian darah pada {day}.",
        "zh": "您在{day}有一次验血。",
    },
    # The visit's logistics (E05-03): where it is, and whose note about the place there is.
    "logistics_place": {
        "en": "{doctor} is at {place}.",
        "ms": "{doctor} berada di {place}.",
        "zh": "{doctor}在{place}。",
    },
    "logistics_no_place": {
        "en": "Nura does not have {doctor}'s address yet.",
        "ms": "Nura belum ada alamat {doctor}.",
        "zh": "Nura还没有{doctor}的地址。",
    },
    "logistics_note_by": {
        "en": "{who} wrote a note about getting to {doctor}.",
        "ms": "{who} menulis nota tentang cara ke {doctor}.",
        "zh": "{who}写了去{doctor}那里要注意的事。",
    },
    "logistics_note_family": {
        "en": "Your family wrote a note about getting to {doctor}.",
        "ms": "Keluarga anda menulis nota tentang cara ke {doctor}.",
        "zh": "您的家人写了去{doctor}那里要注意的事。",
    },
    # The planner's own proposals (T2, `app.reasoning.visits.planner`): "Nura suggests" rows,
    # never a booking and never a claim about what is wrong — only what the record already
    # holds that a visit would follow up on.
    "visit_suggestion_follow_up_day": {
        "en": "Nura suggests you see your doctor again around {day}.",
        "ms": "Nura mencadangkan anda jumpa doktor anda lagi sekitar {day}.",
        "zh": "Nura建议您在{day}前后再看一次医生。",
    },
    "visit_suggestion_medicine_review": {
        "en": "Nura suggests you see your doctor about your medicines.",
        "ms": "Nura mencadangkan anda jumpa doktor anda tentang ubat anda.",
        "zh": "Nura建议您就您的药物去看医生。",
    },
    "visit_suggestion_test_coming": {
        "en": "Nura suggests you see your doctor again about your blood test.",
        "ms": "Nura mencadangkan anda jumpa doktor anda lagi tentang ujian darah anda.",
        "zh": "Nura建议您为验血再看一次医生。",
    },
    "visit_suggestion_screening": {
        "en": "Nura suggests a visit to your doctor.",
        "ms": "Nura mencadangkan lawatan ke doktor anda.",
        "zh": "Nura建议您去看医生。",
    },
}
"""Every line the visit loop can say that is not a thing for him to do, by key and language."""

# @patient action
ACTION_TEMPLATES: Mapping[str, Mapping[str, str]] = {
    # What to bring: on the day of the visit.
    "bring_bp_book": {
        "en": "Bring your blood pressure book on {day}.",
        "ms": "Bawa buku tekanan darah anda pada {day}.",
        "zh": "{day}，带上您的血压本。",
    },
    "bring_medicines": {
        "en": "Bring your medicines in their boxes on {day}.",
        "ms": "Bawa ubat anda dalam kotaknya pada {day}.",
        "zh": "{day}，带上您的药和药盒。",
    },
    "bring_bp_book_next_time": {
        "en": "Bring your blood pressure book on {day}.",
        "ms": "Bawa buku tekanan darah anda pada {day}.",
        "zh": "{day}，带上您的血压本。",
    },
    # The red flag. Same-day, a person, what happened, never a diagnosis.
    "call_doctor_today": {
        "en": "Call {doctor} today.",
        "ms": "Telefon {doctor} hari ini.",
        "zh": "今天就打电话给{doctor}。",
    },
    "tell_carer_today": {
        "en": "Tell {carer} about {what} today.",
        "ms": "Beritahu {carer} tentang {what} hari ini.",
        "zh": "今天就把{what}的事告诉{carer}。",
    },
    "tell_doctor_about": {
        "en": "Tell {doctor} about {what} today.",
        "ms": "Beritahu {doctor} tentang {what} hari ini.",
        "zh": "今天就把{what}的事告诉{doctor}。",
    },
    # Actions heard at the visit, as memos. `ActionKind` in `summary.py` names these.
    "weigh_every_morning": {
        "en": "Every morning, stand on the scale before breakfast.",
        "ms": "Setiap pagi, timbang berat sebelum sarapan.",
        "zh": "每天早上，早餐前站上体重秤。",
    },
    "bp_every_morning": {
        "en": "Every morning, take your blood pressure before breakfast.",
        "ms": "Setiap pagi, ambil tekanan darah sebelum sarapan.",
        "zh": "每天早上，早餐前量血压。",
    },
    "no_food_after_midnight": {
        "en": "Eat nothing after 12 midnight on {day}.",
        "ms": "Jangan makan selepas 12 tengah malam pada {day}.",
        "zh": "{day}半夜12点后不要吃东西。",
    },
    "lighter_dinners": {
        "en": "Every evening, eat a lighter dinner.",
        "ms": "Setiap malam, makan lebih ringan.",
        "zh": "每天晚上，晚餐吃得清淡一些。",
    },
    "walk_every_day": {
        "en": "Every day, walk for {minutes} minutes.",
        "ms": "Setiap hari, berjalan selama {minutes} minit.",
        "zh": "每天走{minutes}分钟。",
    },
    # The visit's logistics (E05-03): who drives him, and the last paper to bring.
    "logistics_driver": {
        "en": "{who} will drive you to {doctor} on {day}.",
        "ms": "{who} akan menghantar anda ke {doctor} pada {day}.",
        "zh": "{who}会在{day}开车送您去见{doctor}。",
    },
    "logistics_driver_family": {
        "en": "Your family will drive you to {doctor} on {day}.",
        "ms": "Keluarga anda akan menghantar anda ke {doctor} pada {day}.",
        "zh": "您的家人会在{day}开车送您去见{doctor}。",
    },
    "logistics_driver_ask": {
        "en": "{who} will tell you who is driving you to {doctor} on {day}.",
        "ms": "{who} akan beritahu anda siapa yang menghantar anda ke {doctor} pada {day}.",
        "zh": "{who}会告诉您，{day}谁开车送您去见{doctor}。",
    },
    "bring_last_letter": {
        "en": "Bring your hospital letter on {day}.",
        "ms": "Bawa surat hospital anda pada {day}.",
        "zh": "{day}，带上您的出院信。",
    },
}
"""Every line that tells him to do something: it says when, and who does the next thing,
and the verifier holds it to that (`kind="action"`)."""

TEMPLATES: Mapping[str, Mapping[str, str]] = {**LINE_TEMPLATES, **ACTION_TEMPLATES}

# @patient phrase
NOTE_LABEL: Mapping[str, str] = {"en": "{who}'s note", "ms": "Nota {who}", "zh": "{who}写的话"}
"""The label over the chief's own note about a place, shown as she wrote it (E05-03)."""

# @patient phrase
FAMILY_NOTE_LABEL: Mapping[str, str] = {
    "en": "Your family's note",
    "ms": "Nota keluarga anda",
    "zh": "您家人写的话",
}
"""The same label when the writer's account has no name to show yet: never an empty slot."""

# @patient phrase
DRIVE_TASK: Mapping[str, str] = {
    "en": "drive {name} to {doctor}",
    "ms": "hantar {name} ke {doctor}",
    "zh": "开车送{name}去见{doctor}",
}
"""What a drive task says on the family's list: one label, filled with his name and the
doctor's (E05-03, E12-03)."""
ACTION_KEYS = frozenset(ACTION_TEMPLATES)

# --- what a slot may hold ------------------------------------------------------------------

_NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ .'’\-])*$")
"""A person's or a doctor's name: letters in any script, spaces, dots, apostrophes, hyphens.
No digits, no newline, nothing that could be an id or a sentence."""
_WORDS = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ ()'’\-])*$")
"""His words for a thing, from one of the tables above: letters, spaces, brackets, hyphens."""
_WHEN = re.compile(r"^[\w .:一-鿿]{1,40}$")
"""A day-and-date or a time as `day_and_date`/`time_of_day` render them."""
_NUMBER = re.compile(r"^\d{1,3}$")
_PLACE = re.compile(r"^[^\W_](?:[\w .,'’()#/&\-])*$")
"""An address as the directory holds it: letters and digits in any script, and the marks an
address uses. One line; the verifier still reads the whole sentence it goes into."""

SLOT_RULES: Mapping[str, tuple[re.Pattern[str], int]] = {
    "doctor": (_NAME, 60),
    "carer": (_NAME, 60),
    "who": (_NAME, 60),
    "medicine": (_WORDS, 60),
    "other": (_WORDS, 60),
    "thing": (_WORDS, 60),
    "what": (_WORDS, 60),
    "subject": (_WORDS, 60),
    "day": (_WHEN, 40),
    "time": (_WHEN, 40),
    "place": (_PLACE, 120),
    "count": (_NUMBER, 3),
    "minutes": (_NUMBER, 3),
}
"""Every slot a template has, and what it takes. A slot not here takes nothing."""


def check_slot(name: str, value: Any) -> str:
    """The slot value as text, or `NotASlotValue`."""
    rule = SLOT_RULES.get(name)
    if rule is None:
        raise NotASlotValue(f"no template takes a slot named {name!r}")
    pattern, longest = rule
    text = str(value).strip()
    if not text or len(text) > longest or not pattern.match(text):
        raise NotASlotValue(f"{name!r} does not take {text!r}")
    return text


def template(key: str, language: str) -> str:
    lang = language_for(language)
    found = TEMPLATES.get(key)
    if found is None:
        raise NoSuchTemplate(f"no template {key}")
    return found[lang]


def kind_of(key: str) -> Kind:
    """How the verifier reads a line from this template: an action says when and who."""
    return "action" if key in ACTION_KEYS else "line"


def render(key: str, language: str, **slots: Any) -> str:
    """The template filled in. Every slot value is checked against its rule first."""
    checked = {name: check_slot(name, value) for name, value in slots.items()}
    return template(key, language).format(**checked)


def verified(text: str, language: str, kind: Kind = "line") -> str:
    """The line, or `NotPlainEnough`. Notes (a line one word too long) pass; failures do not."""
    problems = [str(f) for f in verify(text, language_for(language), kind) if f.severity != "note"]
    if problems:
        raise NotPlainEnough(text, problems)
    return text


def say(key: str, language: str, kind: Kind | None = None, **slots: Any) -> str:
    """Render and verify in one step: the only way a template reaches a row. The kind is the
    template's own unless the caller narrows it."""
    return verified(render(key, language, **slots), language, kind or kind_of(key))

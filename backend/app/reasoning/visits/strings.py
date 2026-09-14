"""The words of the visit loop: every line a patient reads on a brief, a questions card, a
post-visit summary or a memo, as a template, in English, Malay and Chinese.

Nothing rendered for him is assembled at run time from pieces: each line is one whole
template with `{slots}` for a name, a date or a number, tagged `@patient` so that
`make plain-words` reads it, and the rendered line is checked again by
`app.safety.plain_words.verify` before it is stored (`verified`). A line that fails is
refused (`NotPlainEnough`) and never shown. The sentence for a medicine change is a question
for the doctor, never the change: the model that read the transcript classifies, and the
template speaks.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.db import as_utc
from app.errors import Refusal
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


def language_for(code: str | None) -> str:
    """The language the loop speaks to this profile in."""
    return code if code in LANGUAGES else FALLBACK_LANGUAGE


# --- the day and the date ------------------------------------------------------------------

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
    """Rule 5: "Monday 29 September", on the patient's own clock, in his language."""
    local = as_utc(moment).astimezone(REGION_TZ[region])
    lang = language_for(language)
    weekday = WEEKDAYS[lang][local.weekday()]
    if lang == "zh":
        return f"{weekday} {local.month}月{local.day}日"
    return f"{weekday} {local.day} {MONTHS[lang][local.month - 1]}"


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
        "symptom": "keadaan anda",
        "hypertension": "tekanan darah anda",
        "diabetes": "gula anda",
    },
    "zh": {
        "blood_pressure": "您的血压",
        "blood_sugar": "您的血糖检查",
        "weight": "您的体重",
        "heart_rate": "您的脉搏",
        "lipid_panel": "您的胆固醇检查",
        "kidney": "您的肾脏检查",
        "medicine": "您的药",
        "medication": "您的药",
        "symptom": "您的感觉",
        "hypertension": "您的血压",
        "diabetes": "您的血糖",
    },
}
"""A subject code, in his words. A code not here is spoken as its words with the underscores
taken out, and the verifier decides whether that is plain enough."""

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
        "amlodipine": "pil tekanan darah anda",
        "atorvastatin": "pil kolesterol",
        "metformin": "pil gula",
    },
    "zh": {
        "furosemide": "利水药",
        "frusemide": "利水药",
        "amlodipine": "您的血压药",
        "atorvastatin": "胆固醇药",
        "metformin": "降糖药",
    },
}
"""The glossary of docs/plain-words.md as a table: his name for a medicine first, the
chemical name second and small. A medicine not in the glossary is named as it is."""

# @patient phrase
RED_FLAG_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "chest_pain": "the chest pain",
        "breathless": "the breathlessness",
        "black_stool": "the black stool",
        "fall": "the fall",
        "confusion": "the confusion",
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
        "breathless": "气促",
        "black_stool": "黑便",
        "fall": "跌倒",
        "confusion": "神志不清",
        "one_sided_swelling": "腿肿",
        "worst_headache": "剧烈头痛",
        "sudden_blurring": "眼睛模糊",
        "shaky_and_sweaty": "发抖出汗",
        "fever_on_medicine": "发烧",
    },
}


def subject_words(subject: str, language: str) -> str:
    lang = language_for(language)
    return SUBJECT_WORDS[lang].get(subject, subject.replace("_", " "))


def medicine_words(name: str, language: str) -> str:
    """His name for the medicine first, the chemical name second in brackets in English; in
    Malay and Chinese his name alone, because the verifier's glossary knows the chemical
    name and only the English word beside it. A medicine the glossary has no word for is
    named as it is, and the verifier decides."""
    lang = language_for(language)
    plain = MEDICINE_WORDS[lang].get(name.strip().lower())
    if plain is None:
        return name.strip()
    return f"{plain} ({name.strip().lower()})" if lang == "en" else plain


def red_flag_words(code: str, language: str) -> str:
    lang = language_for(language)
    return RED_FLAG_WORDS[lang].get(code, code.replace("_", " "))


# --- the templates -------------------------------------------------------------------------

# @patient
TEMPLATES: Mapping[str, Mapping[str, str]] = {
    # The brief.
    "visit_with": {
        "en": "You see {doctor} on {day}.",
        "ms": "Anda berjumpa {doctor} pada {day}.",
        "zh": "您在{day}见{doctor}。",
    },
    "visit_about": {
        "en": "This visit is about {purpose}.",
        "ms": "Lawatan ini tentang {purpose}.",
        "zh": "这次看诊是关于{purpose}。",
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
        "en": "Since {day}, {count} things changed about how you are.",
        "ms": "Sejak {day}, {count} perkara berubah tentang keadaan anda.",
        "zh": "自{day}以来，您的情况有{count}处变化。",
    },
    "nothing_changed": {
        "en": "Nothing has changed since {day}.",
        "ms": "Tiada apa yang berubah sejak {day}.",
        "zh": "自{day}以来没有变化。",
    },
    "bring_bp_book": {
        "en": "Bring your blood pressure book.",
        "ms": "Bawa buku tekanan darah anda.",
        "zh": "带上您的血压本。",
    },
    "bring_medicines": {
        "en": "Bring your medicines in their boxes.",
        "ms": "Bawa ubat anda dalam kotaknya.",
        "zh": "带上您的药和药盒。",
    },
    # Questions, from gaps.
    "ask_fact_expired": {
        "en": "Ask {doctor} about {thing} again.",
        "ms": "Tanya {doctor} tentang {thing} sekali lagi.",
        "zh": "再问一问{doctor}关于{thing}。",
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
        "en": "Tell {doctor} that the papers disagree about {thing}.",
        "ms": "Beritahu {doctor} bahawa surat-surat tidak sepakat tentang {thing}.",
        "zh": "告诉{doctor}，文件上关于{thing}的记录不一致。",
    },
    "ask_visit_purpose": {
        "en": "Ask {doctor} what this visit is for.",
        "ms": "Tanya {doctor} untuk apa lawatan ini.",
        "zh": "问{doctor}这次看诊是为了什么。",
    },
    # Questions and memos, from a medicine change heard. A question for the doctor, never
    # the change itself.
    "ask_new_amount": {
        "en": "Ask {doctor} about the new amount of {medicine}.",
        "ms": "Tanya {doctor} tentang jumlah baru {medicine}.",
        "zh": "问{doctor}{medicine}的新用量。",
    },
    "ask_starting": {
        "en": "Ask {doctor} about starting {medicine}.",
        "ms": "Tanya {doctor} tentang mula makan {medicine}.",
        "zh": "问{doctor}关于开始吃{medicine}。",
    },
    "ask_stopping": {
        "en": "Ask {doctor} about stopping {medicine}.",
        "ms": "Tanya {doctor} tentang berhenti makan {medicine}.",
        "zh": "问{doctor}关于停吃{medicine}。",
    },
    "ask_medicine_change": {
        "en": "Ask {doctor} about the change to {medicine}.",
        "ms": "Tanya {doctor} tentang perubahan pada {medicine}.",
        "zh": "问{doctor}关于{medicine}的变化。",
    },
    # The red flag. Same-day, a person, never a diagnosis.
    "call_doctor_today": {
        "en": "Call {doctor} today.",
        "ms": "Telefon {doctor} hari ini.",
        "zh": "今天就给{doctor}打电话。",
    },
    "tell_carer_today": {
        "en": "Tell {carer} today.",
        "ms": "Beritahu {carer} hari ini.",
        "zh": "今天就告诉{carer}。",
    },
    "tell_doctor_about": {
        "en": "Tell {doctor} about {what}.",
        "ms": "Beritahu {doctor} tentang {what}.",
        "zh": "告诉{doctor}关于{what}。",
    },
    # The questions card for him.
    "no_need_to_remember": {
        "en": "You do not need to remember these.",
        "ms": "Anda tidak perlu ingat semua ini.",
        "zh": "您不需要记住这些。",
    },
    # The summary.
    "doctor_said_on": {
        "en": "{doctor} said this on {day}.",
        "ms": "{doctor} berkata begini pada {day}.",
        "zh": "{doctor}在{day}说了这些。",
    },
    "see_again_on": {
        "en": "See {doctor} again on {day}.",
        "ms": "Jumpa {doctor} lagi pada {day}.",
        "zh": "在{day}再去见{doctor}。",
    },
    "doctor_wrote_down": {
        "en": "{doctor} wrote down {thing}.",
        "ms": "{doctor} mencatat {thing}.",
        "zh": "{doctor}记下了{thing}。",
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
    "bring_bp_book_next_time": {
        "en": "Bring your blood pressure book next time.",
        "ms": "Bawa buku tekanan darah anda lain kali.",
        "zh": "下次带上您的血压本。",
    },
    "no_food_after_midnight": {
        "en": "Do not eat after 12 midnight on {day}.",
        "ms": "Jangan makan selepas 12 tengah malam pada {day}.",
        "zh": "{day}半夜12点后不要吃东西。",
    },
    "water_is_ok": {
        "en": "Water is OK.",
        "ms": "Air kosong boleh.",
        "zh": "喝水没问题。",
    },
    "lighter_dinners": {
        "en": "Eat lighter dinners.",
        "ms": "Makan malam lebih ringan.",
        "zh": "晚餐吃得清淡一些。",
    },
    "take_medicines_as_before": {
        "en": "Take your medicines the same way until you see {doctor}.",
        "ms": "Makan ubat anda seperti biasa sehingga jumpa {doctor}.",
        "zh": "见{doctor}之前，照原来的方式吃药。",
    },
    "walk_every_day": {
        "en": "Every day, walk for {minutes} minutes.",
        "ms": "Setiap hari, berjalan selama {minutes} minit.",
        "zh": "每天走{minutes}分钟。",
    },
    "blood_test_on": {
        "en": "You have a blood test on {day}.",
        "ms": "Anda ada ujian darah pada {day}.",
        "zh": "您在{day}有一次验血。",
    },
}
"""Every line the visit loop can say, by key and language. A key not here is not a line
Nura can say to him (`NoSuchTemplate`)."""


def template(key: str, language: str) -> str:
    lang = language_for(language)
    found = TEMPLATES.get(key)
    if found is None:
        raise NoSuchTemplate(f"no template {key}")
    return found[lang]


def render(key: str, language: str, **slots: Any) -> str:
    """The template filled in. Slots are names, dates and numbers; nothing else."""
    return template(key, language).format(**{k: str(v) for k, v in slots.items()})


def verified(text: str, language: str, kind: Kind = "line") -> str:
    """The line, or `NotPlainEnough`. Notes (a line one word too long) pass; failures do not."""
    problems = [str(f) for f in verify(text, language_for(language), kind) if f.severity != "note"]
    if problems:
        raise NotPlainEnough(text, problems)
    return text


def say(key: str, language: str, kind: Kind = "line", **slots: Any) -> str:
    """Render and verify in one step: the only way a template reaches a row."""
    return verified(render(key, language, **slots), language, kind)

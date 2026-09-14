"""The safety strings: every sentence of the emergency card, the not-feeling-well card, the
family notice and the symptom log, in English, Malay and Chinese.

Each line is a template keyed by an id, tagged `@patient` and written to `docs/plain-words.md`:
whole sentences, one idea per line, his names for things, the day and the date, who does
the next thing, no red words, nothing to decode. The decision tables in `app.safety` choose
*which* id; this file holds only the words. `render` fills a template and runs it through
`app.safety.plain_words.verify` before it leaves, so a line that fails the standard is a
`NotPlainWords` refusal and not a card.

No line here tells him to start, stop or change a medicine. The one line about a medicine
he has not taken says to ask before he takes it, and never says how much. No line is a
diagnosis: a red flag is "Call Mei now. Call 995 now." and nothing about what it means.

Identifiers never go through a template: the chief's phone number on the emergency card is
carried beside the sentence as data, for the stranger holding the card, and the medicine's
strength likewise — the sentence says "the water pill (frusemide)", the table beside it says
"40 mg", because a paramedic needs the number and the standard forbids it in his sentences.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date

from app.errors import Refusal
from app.medicines.strings import say_date
from app.safety.plain_words import Kind, verify

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"


class NotPlainWords(Refusal):
    """A rendered line failed docs/plain-words.md. It does not reach him; the template is wrong."""

    def __init__(self, template_id: str, problems: list[str]) -> None:
        super().__init__(f"{template_id}: " + "; ".join(problems))
        self.template_id = template_id
        self.problems = problems


class NoSuchTemplate(Refusal):
    """A decision table named a line this catalogue does not have."""


def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


# --- the emergency card --------------------------------------------------------------------

# @patient
EMERGENCY_CARD: Mapping[str, Mapping[str, str]] = {
    "ec.title": {
        "en": "This is {name}'s emergency card.",
        "ms": "Ini kad kecemasan {name}.",
        "zh": "这是{name}的紧急卡。",
    },
    "ec.show": {
        "en": "Show this card to the doctor or the ambulance.",
        "ms": "Tunjukkan kad ini kepada doktor atau ambulans.",
        "zh": "请把这张卡给医生或救护人员看。",
    },
    "ec.language": {
        "en": "{name} speaks {speaks}.",
        "ms": "{name} bercakap {speaks}.",
        "zh": "{name}说{speaks}。",
    },
    "ec.age": {
        "en": "{name} is {band} years old.",
        "ms": "{name} berumur {band} tahun.",
        "zh": "{name}{band}岁。",
    },
    "ec.condition": {
        "en": "{name} has {condition}.",
        "ms": "{name} ada {condition}.",
        "zh": "{name}有{condition}。",
    },
    "ec.no_condition": {
        "en": "No condition is written down for {name}.",
        "ms": "Tiada penyakit ditulis untuk {name}.",
        "zh": "{name}没有记录的病。",
    },
    "ec.medicine": {
        "en": "{name} takes {medicine}.",
        "ms": "{name} makan {medicine}.",
        "zh": "{name}吃{medicine}。",
    },
    "ec.medicine_when": {
        "en": "That is {amount} {when}.",
        "ms": "Iaitu {amount} {when}.",
        "zh": "{when}{amount}。",
    },
    "ec.high_risk": {
        "en": "Doctors watch {medicine} closely.",
        "ms": "Doktor memantau {medicine} dengan teliti.",
        "zh": "医生会特别留意{medicine}。",
    },
    "ec.no_medicine": {
        "en": "No medicine is written down for {name}.",
        "ms": "Tiada ubat ditulis untuk {name}.",
        "zh": "{name}没有记录的药。",
    },
    "ec.allergy": {
        "en": "{name} is allergic to {thing}.",
        "ms": "{name} alah kepada {thing}.",
        "zh": "{name}对{thing}过敏。",
    },
    "ec.no_allergy": {
        "en": "{name} has no known allergy.",
        "ms": "{name} tiada alahan yang diketahui.",
        "zh": "{name}没有已知的过敏。",
    },
    "ec.blood_type": {
        "en": "{name}'s blood type is {group}.",
        "ms": "Jenis darah {name} ialah {group}.",
        "zh": "{name}的血型是{group}。",
    },
    "ec.chief": {
        "en": "Call {chief} first.",
        "ms": "Hubungi {chief} dahulu.",
        "zh": "请先打给{chief}。",
    },
    "ec.no_chief": {
        "en": "No family contact is written down yet.",
        "ms": "Belum ada nombor keluarga ditulis.",
        "zh": "还没有记录家人的电话。",
    },
    "ec.doctor": {
        "en": "{name} sees {doctor}.",
        "ms": "{name} berjumpa {doctor}.",
        "zh": "{name}看{doctor}。",
    },
    "ec.last_reading": {
        "en": "The last blood pressure was on {date}.",
        "ms": "Tekanan darah terakhir diambil pada {date}.",
        "zh": "最近一次量血压是在{date}那天。",
    },
    "ec.boundary": {
        "en": "This card is not a doctor's advice.",
        "ms": "Kad ini bukan nasihat doktor.",
        "zh": "这张卡不是医生的建议。",
    },
}

# --- the what-to-do-now card -----------------------------------------------------------------

# @patient
WHAT_TO_DO: Mapping[str, Mapping[str, str]] = {
    "nfw.call_chief": {
        "en": "Call {chief} now.",
        "ms": "Hubungi {chief} sekarang.",
        "zh": "现在就打给{chief}。",
    },
    "nfw.call_995": {
        "en": "Call 995 now.",
        "ms": "Hubungi 995 sekarang.",
        "zh": "现在就打995。",
    },
    "nfw.call_999": {
        "en": "Call 999 now.",
        "ms": "Hubungi 999 sekarang.",
        "zh": "现在就打999。",
    },
    "nfw.if_no_answer_995": {
        "en": "If you cannot reach {chief}, call 995 now.",
        "ms": "Jika {chief} tidak menjawab, hubungi 995 sekarang.",
        "zh": "如果找不到{chief}，现在就打995。",
    },
    "nfw.if_no_answer_999": {
        "en": "If you cannot reach {chief}, call 999 now.",
        "ms": "Jika {chief} tidak menjawab, hubungi 999 sekarang.",
        "zh": "如果找不到{chief}，现在就打999。",
    },
    "nfw.chief_knows": {
        "en": "{chief} knows.",
        "ms": "{chief} sudah tahu.",
        "zh": "{chief}已经知道了。",
    },
    "nfw.family_knows": {
        "en": "Your family knows.",
        "ms": "Keluarga anda sudah tahu.",
        "zh": "您的家人已经知道了。",
    },
    "nfw.not_taken": {
        "en": "You have not taken {medicine} today.",
        "ms": "Anda belum makan {medicine} hari ini.",
        "zh": "您今天还没吃{medicine}。",
    },
    "nfw.ask_before": {
        "en": "Ask {who} before you take it.",
        "ms": "Tanya {who} dahulu sebelum anda makan.",
        "zh": "吃之前先问{who}。",
    },
    "nfw.rest": {
        "en": "Sit down and rest.",
        "ms": "Duduk dan berehat.",
        "zh": "请坐下休息。",
    },
    "nfw.water": {
        "en": "Drink water.",
        "ms": "Minum air.",
        "zh": "请喝点水。",
    },
    "nfw.will_call": {
        "en": "{chief} will call you.",
        "ms": "{chief} akan telefon anda.",
        "zh": "{chief}会打给您。",
    },
    "nfw.check_in": {
        "en": "Nura will ask you again in 2 hours.",
        "ms": "Nura akan tanya anda lagi dalam 2 jam.",
        "zh": "Nura会在2小时后再问您。",
    },
    "nfw.wrote": {
        "en": "Nura wrote it down.",
        "ms": "Nura sudah catat.",
        "zh": "Nura已经记下了。",
    },
    "nfw.not_heard": {
        "en": "Nura could not hear you.",
        "ms": "Nura tidak dapat mendengar anda.",
        "zh": "Nura没有听清楚。",
    },
    "nfw.say_again": {
        "en": "Please say it again, or type it.",
        "ms": "Sila cakap sekali lagi, atau taip.",
        "zh": "请再说一次，或者打字。",
    },
}

# --- the notice to the family ---------------------------------------------------------------

# @patient
NOTICE: Mapping[str, Mapping[str, str]] = {
    "notice.not_well": {
        "en": "{patient} is not feeling well.",
        "ms": "{patient} rasa tidak sihat.",
        "zh": "{patient}不舒服。",
    },
    "notice.said": {
        "en": "{patient} said: '{words}'.",
        "ms": "{patient} kata: '{words}'.",
        "zh": "{patient}说：“{words}”。",
    },
    "notice.not_heard": {
        "en": "Nura could not hear the words.",
        "ms": "Nura tidak dapat mendengar kata-katanya.",
        "zh": "Nura没有听清楚。",
    },
    "notice.call_now": {
        "en": "Call {patient} now.",
        "ms": "Hubungi {patient} sekarang.",
        "zh": "现在就打给{patient}。",
    },
    "notice.do_not_wait": {
        "en": "This one we do not wait for.",
        "ms": "Yang ini kita tidak tunggu.",
        "zh": "这个我们不能等。",
    },
    "notice.call_today": {
        "en": "Please call {patient} today.",
        "ms": "Sila telefon {patient} hari ini.",
        "zh": "请今天打给{patient}。",
    },
    "notice.not_taken": {
        "en": "{patient} has not taken {medicine} today.",
        "ms": "{patient} belum makan {medicine} hari ini.",
        "zh": "{patient}今天还没吃{medicine}。",
    },
    "notice.check_in": {
        "en": "How do you feel now?",
        "ms": "Bagaimana rasa anda sekarang?",
        "zh": "您现在感觉怎么样？",
    },
}

# --- the symptom log -----------------------------------------------------------------------

# @patient
SYMPTOM_LOG: Mapping[str, Mapping[str, str]] = {
    "sym.felt": {
        "en": "{name} felt {symptom} on {date}.",
        "ms": "{name} rasa {symptom} pada {date}.",
        "zh": "{name}在{date}感到{symptom}。",
    },
    "sym.not_well": {
        "en": "{name} was not feeling well on {date}.",
        "ms": "{name} rasa tidak sihat pada {date}.",
        "zh": "{name}在{date}不舒服。",
    },
    "sym.severity": {
        "en": "It was {severity}.",
        "ms": "Rasanya {severity}.",
        "zh": "程度{severity}。",
    },
    "sym.since": {
        "en": "It started {since}.",
        "ms": "Ia bermula {since}.",
        "zh": "从{since}开始。",
    },
    "sym.by_voice": {
        "en": "{name} said this by voice.",
        "ms": "{name} cakap ini dengan suara.",
        "zh": "{name}是用语音说的。",
    },
    "sym.typed": {
        "en": "{name} typed this.",
        "ms": "{name} taip ini.",
        "zh": "{name}是打字说的。",
    },
    "sym.none": {
        "en": "Nothing was written down since {date}.",
        "ms": "Tiada apa-apa ditulis sejak {date}.",
        "zh": "从{date}起没有记录。",
    },
    "sym.wrote": {
        "en": "Nura wrote it down.",
        "ms": "Nura sudah catat.",
        "zh": "Nura已经记下了。",
    },
}

# --- his words for things that fill the slots ---------------------------------------------

# @patient phrase
SYMPTOM_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "tired": "tired",
        "dizzy": "dizzy",
        "headache": "a headache",
        "nausea": "sick in the stomach",
        "vomiting": "like vomiting",
        "cough": "a cough",
        "fever": "a fever",
        "stomach_pain": "a stomach pain",
        "poor_appetite": "no appetite",
        "cannot_sleep": "unable to sleep",
        "leg_swelling": "swollen legs",
        "weak": "weak",
        "joint_pain": "pain in the joints",
        "diarrhoea": "a runny stomach",
        "constipation": "unable to pass motion",
        "itch": "itchy",
        "not_well": "not well",
        "chest_pain": "chest pain",
        "breathless_at_rest": "short of breath",
        "one_sided_swelling": "swelling on one side",
        "worst_headache": "the worst headache ever",
        "sudden_blurring": "sudden blurring of the eyes",
        "fall": "a fall",
        "confusion": "confused",
        "shaky_sweaty": "shaky and sweaty",
    },
    "ms": {
        "tired": "letih",
        "dizzy": "pening",
        "headache": "sakit kepala",
        "nausea": "loya",
        "vomiting": "nak muntah",
        "cough": "batuk",
        "fever": "demam",
        "stomach_pain": "sakit perut",
        "poor_appetite": "tak selera",
        "cannot_sleep": "susah tidur",
        "leg_swelling": "kaki bengkak",
        "weak": "lemah",
        "joint_pain": "sakit sendi",
        "diarrhoea": "cirit-birit",
        "constipation": "sembelit",
        "itch": "gatal",
        "not_well": "tidak sihat",
        "chest_pain": "sakit dada",
        "breathless_at_rest": "sesak nafas",
        "one_sided_swelling": "bengkak sebelah",
        "worst_headache": "sakit kepala paling teruk",
        "sudden_blurring": "mata kabur tiba-tiba",
        "fall": "jatuh",
        "confusion": "keliru",
        "shaky_sweaty": "menggigil dan berpeluh",
    },
    "zh": {
        "tired": "累",
        "dizzy": "头晕",
        "headache": "头痛",
        "nausea": "恶心",
        "vomiting": "想吐",
        "cough": "咳嗽",
        "fever": "发烧",
        "stomach_pain": "肚子痛",
        "poor_appetite": "没胃口",
        "cannot_sleep": "睡不着",
        "leg_swelling": "腿肿",
        "weak": "无力",
        "joint_pain": "关节痛",
        "diarrhoea": "拉肚子",
        "constipation": "便秘",
        "itch": "痒",
        "not_well": "不舒服",
        "chest_pain": "胸痛",
        "breathless_at_rest": "喘不过气",
        "one_sided_swelling": "一边肿",
        "worst_headache": "最厉害的头痛",
        "sudden_blurring": "突然看不清",
        "fall": "跌倒",
        "confusion": "糊涂",
        "shaky_sweaty": "发抖出汗",
    },
}
"""How each symptom or red-flag code is said back, by code. The same words every time."""

# @patient phrase
SEVERITY_WORDS: Mapping[str, Mapping[int, str]] = {
    "en": {1: "a little", 2: "quite a lot", 3: "very bad"},
    "ms": {1: "sedikit", 2: "agak banyak", 3: "teruk sangat"},
    "zh": {1: "一点点", 2: "比较多", 3: "很严重"},
}

# @patient phrase
SINCE_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "just_now": "just now",
        "this_morning": "this morning",
        "since_yesterday": "yesterday",
        "few_days": "a few days ago",
        "about_a_week": "about a week ago",
        "longer": "some weeks ago",
    },
    "ms": {
        "just_now": "tadi",
        "this_morning": "pagi ini",
        "since_yesterday": "semalam",
        "few_days": "beberapa hari lepas",
        "about_a_week": "kira-kira seminggu lepas",
        "longer": "beberapa minggu lepas",
    },
    "zh": {
        "just_now": "刚刚",
        "this_morning": "今天早上",
        "since_yesterday": "昨天",
        "few_days": "几天前",
        "about_a_week": "大约一星期前",
        "longer": "几个星期前",
    },
}

# @patient phrase
WHEN_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "od": "every morning",
        "bd": "every morning and every night",
        "tds": "3 times a day",
        "qds": "4 times a day",
        "weekly": "once a week",
        "prn": "when needed",
    },
    "ms": {
        "od": "setiap pagi",
        "bd": "setiap pagi dan setiap malam",
        "tds": "3 kali sehari",
        "qds": "4 kali sehari",
        "weekly": "sekali seminggu",
        "prn": "bila perlu",
    },
    "zh": {
        "od": "每天早上",
        "bd": "每天早上和晚上",
        "tds": "每天3次",
        "qds": "每天4次",
        "weekly": "每星期一次",
        "prn": "需要时",
    },
}

# @patient phrase
LANGUAGE_NAMES: Mapping[str, Mapping[str, str]] = {
    "en": {"en": "English", "ms": "Malay", "zh": "Chinese", "ta": "Tamil"},
    "ms": {"en": "Bahasa Inggeris", "ms": "Bahasa Melayu", "zh": "Bahasa Cina", "ta": "Bahasa Tamil"},
    "zh": {"en": "英语", "ms": "马来语", "zh": "华语", "ta": "泰米尔语"},
}

# @patient phrase
CONDITION_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "hypertension": "high blood pressure",
        "blood_pressure": "high blood pressure",
        "diabetes": "sugar sickness",
        "blood_sugar": "sugar sickness",
        "heart_failure": "a weak heart",
        "heart_disease": "a heart condition",
        "atrial_fibrillation": "an uneven heartbeat",
        "kidney_disease": "weak kidneys",
        "kidney": "weak kidneys",
        "stroke": "had a stroke before",
        "asthma": "asthma",
        "copd": "a lung condition",
        "cholesterol": "high cholesterol",
        "gout": "gout",
        "dementia": "memory loss",
    },
    "ms": {
        "hypertension": "darah tinggi",
        "blood_pressure": "darah tinggi",
        "diabetes": "kencing manis",
        "blood_sugar": "kencing manis",
        "heart_failure": "jantung lemah",
        "heart_disease": "masalah jantung",
        "atrial_fibrillation": "degupan jantung tidak sekata",
        "kidney_disease": "buah pinggang lemah",
        "kidney": "buah pinggang lemah",
        "stroke": "pernah kena strok",
        "asthma": "asma",
        "copd": "masalah paru-paru",
        "cholesterol": "kolesterol tinggi",
        "gout": "gout",
        "dementia": "hilang ingatan",
    },
    "zh": {
        "hypertension": "高血压",
        "blood_pressure": "高血压",
        "diabetes": "糖尿病",
        "blood_sugar": "糖尿病",
        "heart_failure": "心脏无力",
        "heart_disease": "心脏病",
        "atrial_fibrillation": "心跳不齐",
        "kidney_disease": "肾脏无力",
        "kidney": "肾脏无力",
        "stroke": "中过风",
        "asthma": "哮喘",
        "copd": "肺病",
        "cholesterol": "胆固醇高",
        "gout": "痛风",
        "dementia": "记性不好",
    },
}
"""The plain words for the condition codes a clinician's control word is recorded under.
A code not here is said as it is written, with its underscores taken out."""

# @patient phrase
HIGH_RISK_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "anticoagulant": "the blood thinner",
        "insulin": "the insulin",
        "cardiac_glycoside": "the heart tablet",
        "antimetabolite": "the joint medicine",
        "opioid": "the strong pain medicine",
        "high_risk": "this medicine",
    },
    "ms": {
        "anticoagulant": "ubat cair darah",
        "insulin": "insulin",
        "cardiac_glycoside": "ubat jantung",
        "antimetabolite": "ubat sendi",
        "opioid": "ubat sakit yang kuat",
        "high_risk": "ubat ini",
    },
    "zh": {
        "anticoagulant": "薄血药",
        "insulin": "胰岛素",
        "cardiac_glycoside": "心脏药",
        "antimetabolite": "关节药",
        "opioid": "强效止痛药",
        "high_risk": "这个药",
    },
}

# @patient phrase
BLOOD_GROUP_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "O+": "O positive", "O-": "O negative", "A+": "A positive", "A-": "A negative",
        "B+": "B positive", "B-": "B negative", "AB+": "A B positive", "AB-": "A B negative",
    },
    "ms": {
        "O+": "O positif", "O-": "O negatif", "A+": "A positif", "A-": "A negatif",
        "B+": "B positif", "B-": "B negatif", "AB+": "A B positif", "AB-": "A B negatif",
    },
    "zh": {
        "O+": "O型阳性", "O-": "O型阴性", "A+": "A型阳性", "A-": "A型阴性",
        "B+": "B型阳性", "B-": "B型阴性", "AB+": "A B型阳性", "AB-": "A B型阴性",
    },
}

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}

# @patient phrase
YOUR_MEDICINE: Mapping[str, str] = {"en": "your medicine", "ms": "ubat anda", "zh": "您的药"}


TEMPLATES: Mapping[str, Mapping[str, str]] = {
    **EMERGENCY_CARD,
    **WHAT_TO_DO,
    **NOTICE,
    **SYMPTOM_LOG,
}

KIND_OF: Mapping[str, Kind] = {"ec.title": "headline"}
"""How the verifier reads a line, where it is not a whole line he hears."""


def template(template_id: str, language: str) -> str:
    by_language = TEMPLATES.get(template_id)
    if by_language is None:
        raise NoSuchTemplate(f"no template {template_id}")
    return by_language.get(language_of(language)) or by_language[DEFAULT_LANGUAGE]


def render(template_id: str, language: str, **slots: str | date) -> str:
    """One line, filled and verified. Every line that reaches him comes through here.

    A `date` slot is said in his language ("Khamis 3 September", "9月3日星期四") and checked
    in English ("Thursday 3 September"): the verifier's rule 5 is about the form — the day
    beside the date — and it knows the English day names; the Malay and Chinese forms are
    `say_date`'s and come from one table.
    """
    lang = language_of(language)
    said = {k: say_date(v, lang) if isinstance(v, date) else v for k, v in slots.items()}
    checked = {k: say_date(v, "en") if isinstance(v, date) else v for k, v in slots.items()}
    text = template(template_id, lang).format(**said)
    failures = [
        f"rule {finding.rule} — {finding.problem}"
        for finding in verify(
            template(template_id, lang).format(**checked), lang, KIND_OF.get(template_id, "line")
        )
        if finding.severity == "fail"
    ]
    if failures:
        raise NotPlainWords(template_id, failures)
    return text


def phrase(table: Mapping[str, Mapping[str, str]], language: str, code: str) -> str:
    """A word from a phrase table in the language, falling back to English, then to the code
    with its underscores taken out — a name is never dropped for want of a translation."""
    by_code = table.get(language_of(language)) or table[DEFAULT_LANGUAGE]
    return by_code.get(code) or table[DEFAULT_LANGUAGE].get(code) or code.replace("_", " ")


def catalogue() -> Iterator[tuple[str, str, str]]:
    """Every template, as (id, language, text), for the tests that verify them all."""
    for template_id, by_language in TEMPLATES.items():
        for language, text in by_language.items():
            yield template_id, language, text

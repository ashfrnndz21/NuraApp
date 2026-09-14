"""The safety strings: every sentence of the emergency card, the not-feeling-well card, the
family notice and the symptom log, in English, Malay and Chinese.

Each line is a template keyed by an id, tagged `@patient` and written to `docs/plain-words.md`:
whole sentences, one idea per line, his names for things, the day and the date, who does
the next thing, no red words, nothing to decode. The decision tables in `app.safety` choose
*which* id; this file holds only the words. `render` fills a template and runs it through
`app.safety.plain_words.verify` before it leaves — the what-to-do lines as the `action`
kind, so a line that does not say who does the next thing and when fails in CI — and a line
that fails the standard is a `NotPlainWords` refusal and not a card.

No line here tells him to start, stop or change a medicine. The one line about a medicine
nobody tapped Taken on says Nura has no note of it and to ask before he takes it, never how
much. No line is a diagnosis: a red flag is "Mei knows already. Call the ambulance now on
995. After that, call Mei." and nothing about what it means. No line tells him to drink: fluid is a
clinical matter for a man with a weak heart, so the rest card says rest and nothing else.

Identifiers never go through a template: the chief's phone number on the emergency card is
carried beside the sentence as data, for the stranger holding the card, and the medicine's
strength likewise — the sentence says "the water pill (frusemide)", the table beside it says
"40 mg", because a paramedic needs the number and the standard forbids it in his sentences.
The notice to the family quotes the table's word for what Nura heard, never his transcript,
and says so: "Nura heard this: chest pain."
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date

from app.errors import Refusal
from app.medicines.strings import say_date
from app.safety.plain_words import Kind, verify
from app.safety.symptoms import severity_word

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
        "en": "Show this card to the doctor or the ambulance crew.",
        "ms": "Tunjukkan kad ini kepada doktor atau krew ambulans.",
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
        "en": "Nura has no note of a condition for {name}.",
        "ms": "Nura tiada catatan penyakit untuk {name}.",
        "zh": "Nura没有{name}的病的记录。",
    },
    "ec.medicine": {
        "en": "{name} takes {medicine}.",
        "ms": "{name} makan {medicine}.",
        "zh": "{name}吃{medicine}。",
    },
    "ec.medicine_when": {
        "en": "{name} takes {amount} {when}.",
        "ms": "{name} makan {amount} {when}.",
        "zh": "{name}{when}吃{amount}。",
    },
    "ec.high_risk": {
        "en": "{name}'s doctor watches {medicine} closely.",
        "ms": "Doktor {name} memantau {medicine} dengan teliti.",
        "zh": "{name}的医生会特别留意{medicine}。",
    },
    "ec.no_medicine": {
        "en": "Nura has no note of a medicine for {name}.",
        "ms": "Nura tiada catatan ubat untuk {name}.",
        "zh": "Nura没有{name}的药的记录。",
    },
    "ec.allergy": {
        "en": "{name} is allergic to {thing}.",
        "ms": "{name} alah kepada {thing}.",
        "zh": "{name}对{thing}过敏。",
    },
    "ec.no_allergy": {
        "en": "{name} has no allergy that Nura knows of.",
        "ms": "{name} tiada alahan yang Nura tahu.",
        "zh": "Nura不知道{name}有什么过敏。",
    },
    "ec.blood_type": {
        "en": "{name}'s blood type is {group}.",
        "ms": "Jenis darah {name} ialah {group}.",
        "zh": "{name}的血型是{group}。",
    },
    "ec.chief_who": {
        "en": "{chief} looks after {name}.",
        "ms": "{chief} menjaga {name}.",
        "zh": "{chief}照顾{name}。",
    },
    "ec.chief": {
        "en": "Call {chief} first.",
        "ms": "Hubungi {chief} dahulu.",
        "zh": "请先打给{chief}。",
    },
    "ec.no_chief": {
        "en": "No family number is written down yet.",
        "ms": "Belum ada nombor keluarga ditulis.",
        "zh": "还没有记录家人的电话号码。",
    },
    "ec.doctor": {
        "en": "{name} sees {doctor}.",
        "ms": "{name} berjumpa {doctor}.",
        "zh": "{name}看{doctor}。",
    },
    "ec.clinic": {
        "en": "{name} goes to {clinic}.",
        "ms": "{name} pergi ke {clinic}.",
        "zh": "{name}去{clinic}看病。",
    },
    "ec.ambulance": {
        "en": "The ambulance number is {number}.",
        "ms": "Nombor ambulans ialah {number}.",
        "zh": "救护车的号码是{number}。",
    },
    "ec.last_reading": {
        "en": "{name}'s blood pressure was last written down on {date}.",
        "ms": "Tekanan darah {name} terakhir ditulis pada {date}.",
        "zh": "{name}最近一次记录血压是在{date}那天。",
    },
    "ec.boundary": {
        "en": "This card is not a doctor's advice.",
        "ms": "Kad ini bukan nasihat doktor.",
        "zh": "这张卡不是医生的意见。",
    },
}

# --- the what-to-do-now card -----------------------------------------------------------------

# @patient action
WHAT_TO_DO: Mapping[str, Mapping[str, str]] = {
    "nfw.chief_knows": {
        "en": "{chief} knows already.",
        "ms": "{chief} sudah tahu.",
        "zh": "{chief}已经知道了。",
    },
    "nfw.family_knows": {
        "en": "Your family knows already and will call you.",
        "ms": "Keluarga anda sudah tahu dan akan telefon anda.",
        "zh": "您的家人已经知道了，会打给您。",
    },
    "nfw.call_995": {
        "en": "Call the ambulance now on 995.",
        "ms": "Hubungi ambulans sekarang di talian 995.",
        "zh": "现在就打995叫救护车。",
    },
    "nfw.call_999": {
        "en": "Call the ambulance now on 999.",
        "ms": "Hubungi ambulans sekarang di talian 999.",
        "zh": "现在就打999叫救护车。",
    },
    "nfw.then_call_chief": {
        "en": "After that, call {chief}.",
        "ms": "Selepas itu, hubungi {chief}.",
        "zh": "然后再打给{chief}。",
    },
    "nfw.not_taken": {
        "en": "Nura has no note that you took {medicine} today.",
        "ms": "Nura tiada catatan yang anda makan {medicine} hari ini.",
        "zh": "Nura没有您今天吃了{medicine}的记录。",
    },
    "nfw.ask_before": {
        "en": "Ask {who} before you take {medicine}.",
        "ms": "Tanya {who} dahulu sebelum anda makan {medicine}.",
        "zh": "吃{medicine}之前先问{who}。",
    },
    "nfw.rest": {
        "en": "Sit down and rest now.",
        "ms": "Duduk dan berehat sekarang.",
        "zh": "现在请坐下休息。",
    },
    "nfw.will_call": {
        "en": "{chief} will call you today.",
        "ms": "{chief} akan telefon anda hari ini.",
        "zh": "{chief}今天会打给您。",
    },
    "nfw.check_in": {
        "en": "Nura will ask you again in 2 hours.",
        "ms": "Nura akan tanya anda lagi dalam 2 jam.",
        "zh": "Nura会在2小时后再问您。",
    },
    "nfw.not_heard": {
        "en": "Nura could not hear you.",
        "ms": "Nura tidak dapat mendengar anda.",
        "zh": "Nura没有听清楚您说的话。",
    },
    "nfw.say_again": {
        "en": "Please tell Nura again.",
        "ms": "Sila beritahu Nura sekali lagi.",
        "zh": "请再告诉Nura一次。",
    },
    "nfw.type_instead": {
        "en": "You can type it to Nura instead.",
        "ms": "Anda boleh taip kepada Nura pula.",
        "zh": "您也可以打字告诉Nura。",
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
    "notice.heard": {
        "en": "Nura heard this: {words}.",
        "ms": "Nura dengar ini: {words}.",
        "zh": "Nura听到的是：{words}。",
    },
    "notice.not_heard": {
        "en": "Nura could not hear what {patient} said.",
        "ms": "Nura tidak dapat mendengar apa yang {patient} kata.",
        "zh": "Nura没有听清楚{patient}说的话。",
    },
    "notice.call_now": {
        "en": "Call {patient} now.",
        "ms": "Telefon {patient} sekarang.",
        "zh": "现在就打电话给{patient}。",
    },
    "notice.do_not_wait": {
        "en": "This one we do not wait for.",
        "ms": "Yang ini kita tidak tunggu.",
        "zh": "这个我们不等。",
    },
    "notice.call_today": {
        "en": "Please call {patient} today.",
        "ms": "Sila telefon {patient} hari ini.",
        "zh": "请今天打给{patient}。",
    },
    "notice.not_taken": {
        "en": "Nura has no note that {patient} took {medicine} today.",
        "ms": "Nura tiada catatan yang {patient} makan {medicine} hari ini.",
        "zh": "Nura没有{patient}今天吃了{medicine}的记录。",
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
    "sym.not_well": {
        "en": "{name} was not feeling well on {date}.",
        "ms": "{name} rasa tidak sihat pada {date}.",
        "zh": "{name}在{date}不舒服。",
    },
    "sym.severity": {
        "en": "It was {severity}.",
        "ms": "Rasanya {severity}.",
        "zh": "感觉{severity}。",
    },
    "sym.since": {
        "en": "It started {since}.",
        "ms": "Ia bermula {since}.",
        "zh": "从{since}开始。",
    },
    "sym.by_voice": {
        "en": "{name} said this out loud.",
        "ms": "{name} cakap ini dengan suara.",
        "zh": "{name}是用语音说的。",
    },
    "sym.typed": {
        "en": "{name} wrote this down.",
        "ms": "{name} tulis ini sendiri.",
        "zh": "{name}是打字写的。",
    },
    "sym.none": {
        "en": "Nobody wrote anything down since {date}.",
        "ms": "Tiada sesiapa menulis apa-apa sejak {date}.",
        "zh": "从{date}起没有人记下什么。",
    },
}

# @patient
SYMPTOM_LINES: Mapping[str, Mapping[str, str]] = {
    "tired": {
        "en": "{name} felt tired on {date}.",
        "ms": "{name} rasa letih pada {date}.",
        "zh": "{name}在{date}感到累。",
    },
    "dizzy": {
        "en": "{name} felt dizzy on {date}.",
        "ms": "{name} rasa pening pada {date}.",
        "zh": "{name}在{date}感到头晕。",
    },
    "headache": {
        "en": "{name} had a headache on {date}.",
        "ms": "{name} sakit kepala pada {date}.",
        "zh": "{name}在{date}头痛。",
    },
    "nausea": {
        "en": "{name} felt sick in the stomach on {date}.",
        "ms": "{name} rasa loya pada {date}.",
        "zh": "{name}在{date}感到恶心。",
    },
    "vomiting": {
        "en": "{name} vomited on {date}.",
        "ms": "{name} muntah pada {date}.",
        "zh": "{name}在{date}吐了。",
    },
    "cough": {
        "en": "{name} had a cough on {date}.",
        "ms": "{name} batuk pada {date}.",
        "zh": "{name}在{date}咳嗽。",
    },
    "fever": {
        "en": "{name} had a fever on {date}.",
        "ms": "{name} demam pada {date}.",
        "zh": "{name}在{date}发烧。",
    },
    "stomach_pain": {
        "en": "{name} had a stomach pain on {date}.",
        "ms": "{name} sakit perut pada {date}.",
        "zh": "{name}在{date}肚子痛。",
    },
    "poor_appetite": {
        "en": "{name} had no appetite on {date}.",
        "ms": "{name} tak selera makan pada {date}.",
        "zh": "{name}在{date}没胃口。",
    },
    "cannot_sleep": {
        "en": "{name} could not sleep on {date}.",
        "ms": "{name} susah tidur pada {date}.",
        "zh": "{name}在{date}睡不着。",
    },
    "leg_swelling": {
        "en": "{name}'s legs were swollen on {date}.",
        "ms": "Kaki {name} bengkak pada {date}.",
        "zh": "{name}在{date}腿肿。",
    },
    "weak": {
        "en": "{name} felt weak on {date}.",
        "ms": "{name} rasa lemah pada {date}.",
        "zh": "{name}在{date}感到无力。",
    },
    "joint_pain": {
        "en": "{name} had pain in the joints on {date}.",
        "ms": "{name} sakit sendi pada {date}.",
        "zh": "{name}在{date}关节痛。",
    },
    "diarrhoea": {
        "en": "{name} had a runny stomach on {date}.",
        "ms": "{name} cirit-birit pada {date}.",
        "zh": "{name}在{date}拉肚子。",
    },
    "constipation": {
        "en": "{name} could not pass motion on {date}.",
        "ms": "{name} sembelit pada {date}.",
        "zh": "{name}在{date}便秘。",
    },
    "itch": {
        "en": "{name} felt itchy on {date}.",
        "ms": "{name} rasa gatal pada {date}.",
        "zh": "{name}在{date}感到痒。",
    },
    "chest_tightness": {
        "en": "{name} felt chest pain on {date}.",
        "ms": "{name} rasa sakit dada pada {date}.",
        "zh": "{name}在{date}感到胸痛。",
    },
    "breathless_at_rest": {
        "en": "{name} felt short of breath on {date}.",
        "ms": "{name} rasa sesak nafas pada {date}.",
        "zh": "{name}在{date}感到喘不过气。",
    },
    "one_sided_swelling": {
        "en": "{name} had swelling on one side on {date}.",
        "ms": "{name} bengkak sebelah pada {date}.",
        "zh": "{name}在{date}一边肿了。",
    },
    "worst_headache": {
        "en": "{name} had the worst headache ever on {date}.",
        "ms": "{name} sakit kepala paling teruk pada {date}.",
        "zh": "{name}在{date}头痛得最厉害。",
    },
    "sudden_blurring": {
        "en": "{name}'s eyes went blurry all of a sudden on {date}.",
        "ms": "Mata {name} kabur tiba-tiba pada {date}.",
        "zh": "{name}在{date}眼睛突然看不清。",
    },
    "fall": {
        "en": "{name} had a fall on {date}.",
        "ms": "{name} jatuh pada {date}.",
        "zh": "{name}在{date}跌倒了。",
    },
    "confusion": {
        "en": "{name} felt confused on {date}.",
        "ms": "{name} rasa keliru pada {date}.",
        "zh": "{name}在{date}感到糊涂。",
    },
    "shaky_sweaty": {
        "en": "{name} felt shaky and sweaty on {date}.",
        "ms": "{name} rasa menggigil dan berpeluh pada {date}.",
        "zh": "{name}在{date}又发抖又出汗。",
    },
}
"""One whole sentence per symptom or red-flag code: "had a cough", "vomited", "could not
sleep" — a shared "felt {word}" fits only the adjectives, and "felt like vomiting" for a man
who vomited changes what his daughter is told."""

# --- his words for things that fill the slots ---------------------------------------------

# @patient phrase
SYMPTOM_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "tired": "tired",
        "dizzy": "dizzy",
        "headache": "a headache",
        "nausea": "sick in the stomach",
        "vomiting": "vomiting",
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
        "chest_tightness": "chest pain",
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
        "vomiting": "muntah",
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
        "chest_tightness": "sakit dada",
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
        "vomiting": "呕吐",
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
        "chest_tightness": "胸痛",
        "breathless_at_rest": "喘不过气",
        "one_sided_swelling": "一边肿",
        "worst_headache": "最厉害的头痛",
        "sudden_blurring": "突然看不清",
        "fall": "跌倒",
        "confusion": "糊涂",
        "shaky_sweaty": "发抖又出汗",
    },
}
"""What Nura heard, by code, for the notice ("Nura heard this: a fall."). The same words
every time; never the transcript."""

# @patient phrase
SEVERITY_WORDS: Mapping[str, Mapping[int, str]] = {
    "en": {1: "only a little", 2: "quite bad", 3: "very bad"},
    "ms": {1: "sedikit saja", 2: "agak teruk", 3: "teruk sangat"},
    "zh": {1: "只有一点", 2: "比较严重", 3: "很严重"},
}
"""The three levels said back. One vocabulary: `app.safety.symptoms.severity_word` hears and
says the same words, and a test holds the two tables together."""

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
    **{f"sym.{code}": by_language for code, by_language in SYMPTOM_LINES.items()},
}

KIND_OF: Mapping[str, Kind] = {
    "ec.title": "headline",
    **{template_id: "action" for template_id in WHAT_TO_DO},
}
"""How the verifier reads a line, where it is not a whole line he hears: the title is a
headline, and every what-to-do line is an action — it must say who does the next thing and
when, or it fails in CI."""


def template(template_id: str, language: str) -> str:
    by_language = TEMPLATES.get(template_id)
    if by_language is None:
        raise NoSuchTemplate(f"no template {template_id}")
    return by_language.get(language_of(language)) or by_language[DEFAULT_LANGUAGE]


def render(template_id: str, language: str, **slots: str | date) -> str:
    """One line, filled and verified. Every line that reaches him comes through here.

    A `date` slot is said in his language ("Khamis 3 September", "9月3日星期四", `say_date`) and
    the line is verified exactly as he reads it: rule 5 reads a Malay or Chinese date against
    that language's own day names (E05 review, P3), so nothing is swapped to English first.
    """
    lang = language_of(language)
    said = {k: say_date(v, lang) if isinstance(v, date) else v for k, v in slots.items()}
    text = template(template_id, lang).format(**said)
    failures = [
        f"rule {finding.rule} — {finding.problem}"
        for finding in verify(text, lang, KIND_OF.get(template_id, "line"))
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


def severity_said(level: int, language: str) -> str:
    """The word for a level, from the one vocabulary."""
    return severity_word(level, language_of(language))


def catalogue() -> Iterator[tuple[str, str, str]]:
    """Every template, as (id, language, text), for the tests that verify them all."""
    for template_id, by_language in TEMPLATES.items():
        for language, text in by_language.items():
            yield template_id, language, text

"""Every line a feed card says, in his languages, tagged for `make plain-words`.

A card is made of a headline, the body lines, the voice script (the spoken twin) and the
one-line why. Each template here is a whole line: never assembled from pieces at run time,
only filled — `{who}` for the person who does the next thing, `{doctor}` for the doctor's
name, `{day}` for "Monday 14 September", the numbers as digits. `render` fills a template in
the profile's language and `items.create_item` runs the result through
`app.safety.plain_words.verify` before any row is written, so what is checked here at build
time is checked again with the real names and numbers in it.

The rules the lines follow are `docs/plain-words.md`: whole sentences, one idea per line,
his words for things ("your blood pressure book", "your papers", "your tablets"), the day
and the date, who does the next thing, no red words, nothing to decode. The caregiver's
lines at the bottom are not patient strings and are not tagged: her screens keep the fuller
words (docs/plain-words.md §3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.safety.boundary import Surface, boundary_line

# --- what a card says ----------------------------------------------------------------------

# @patient headline
HEADLINES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "now_tablets": "Your tablets today",
        "now_visit": "You see {doctor} today",
        "now_quiet": "A quiet day",
        "reading": "Your blood pressure today",
        "visit": "{doctor} on {day}",
        "memo": "What {doctor} said",
        "reorder": "{medicine} is running low",
        "gate": "That is all that is new",
        "story_reading": "From your blood pressure book",
        "story_paper": "From your papers",
        "story_note": "Your own words",
        "story_count": "The number that only goes up",
        "flag": "This one we do not wait for",
    },
    "ms": {
        "now_tablets": "Ubat anda hari ini",
        "now_visit": "Anda berjumpa {doctor} hari ini",
        "now_quiet": "Hari yang tenang",
        "reading": "Tekanan darah anda hari ini",
        "visit": "{doctor} pada {day}",
        "memo": "Apa yang {doctor} kata",
        "reorder": "{medicine} hampir habis",
        "gate": "Itu sahaja yang baru",
        "story_reading": "Dari buku tekanan darah anda",
        "story_paper": "Dari surat-surat anda",
        "story_note": "Kata-kata anda sendiri",
        "story_count": "Nombor yang hanya naik",
        "flag": "Yang ini kita tidak tunggu",
    },
    "zh": {
        "now_tablets": "您今天的药",
        "now_visit": "您今天见{doctor}",
        "now_quiet": "平静的一天",
        "reading": "您今天的血压",
        "visit": "{day}见{doctor}",
        "memo": "{doctor}说的话",
        "reorder": "您的{medicine}快用完了",
        "gate": "新的就这些了",
        "story_reading": "来自您的血压本",
        "story_paper": "来自您的文件",
        "story_note": "您自己的话",
        "story_count": "只会往上走的数字",
        "flag": "这个我们不等",
    },
}

# @patient
LINES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "en": {
        "now_tablets": (
            "Your tablets for today are on your list.",
            "Take them the way the label says.",
            "Tap Taken when you have had them.",
        ),
        "now_tablets_voice": (
            "Your tablets for today are on your list.",
            "Take them the way the label says.",
            "Tap Taken when you have had them.",
        ),
        "now_visit": (
            "You see {doctor} today.",
            "Bring your blood pressure book and your tablets.",
        ),
        "now_quiet": (
            "Nothing new is waiting for you today.",
            "Swipe up when you want to hear more.",
        ),
        "reading": (
            "Your blood pressure today was {top_number} over {bottom_number}.",
            "It is in your blood pressure book.",
        ),
        "reading_family": ("{who} can see it too.",),
        "reading_alone": ("I wrote it down.",),
        "visit": (
            "You see {doctor} on {day}.",
            "Bring your blood pressure book and your tablets.",
        ),
        "memo": ("At your last visit {doctor} said this:",),
        "gate": (
            "That is all that is new today.",
            "Do you want to keep going?",
            "Swipe up to hear more about you.",
        ),
        "story_reading": (
            "On {day} your blood pressure was {top_number} over {bottom_number}.",
            "It is in your blood pressure book.",
        ),
        "story_paper": (
            "Your {test_name} from {day} is in your papers.",
            "You can show it to {doctor} any time.",
        ),
        "story_note": ("On {day} you wrote this down:",),
        "story_count": (
            "You have written your blood pressure down {count} times.",
            "This number only goes up.",
        ),
        "learning_source": ("This comes from {source_name}.",),
        "flag_family": (
            "You told Nura about {feeling}.",
            "This one we do not wait for.",
            "{who} knows now.",
            "Call {who}, or call {emergency_number}.",
        ),
        "flag_alone": (
            "You told Nura about {feeling}.",
            "This one we do not wait for.",
            "Call {emergency_number} now.",
        ),
    },
    "ms": {
        "now_tablets": (
            "Ubat anda untuk hari ini ada dalam senarai anda.",
            "Ambil ikut apa yang tertulis pada label.",
            "Tekan Sudah Ambil apabila anda sudah makan ubat.",
        ),
        "now_tablets_voice": (
            "Ubat anda untuk hari ini ada dalam senarai anda.",
            "Ambil ikut apa yang tertulis pada label.",
            "Tekan Sudah Ambil apabila anda sudah makan ubat.",
        ),
        "now_visit": (
            "Anda berjumpa {doctor} hari ini.",
            "Bawa buku tekanan darah dan ubat anda.",
        ),
        "now_quiet": (
            "Tiada yang baru menunggu anda hari ini.",
            "Leret ke atas bila anda mahu dengar lagi.",
        ),
        "reading": (
            "Tekanan darah anda hari ini {top_number} atas {bottom_number}.",
            "Ia ada dalam buku tekanan darah anda.",
        ),
        "reading_family": ("{who} juga boleh melihatnya.",),
        "reading_alone": ("Saya sudah tuliskannya.",),
        "visit": (
            "Anda berjumpa {doctor} pada {day}.",
            "Bawa buku tekanan darah dan ubat anda.",
        ),
        "memo": ("Pada lawatan terakhir {doctor} berkata begini:",),
        "gate": (
            "Itu sahaja yang baru hari ini.",
            "Mahu terus?",
            "Leret ke atas untuk dengar lagi tentang anda.",
        ),
        "story_reading": (
            "Pada {day} tekanan darah anda {top_number} atas {bottom_number}.",
            "Ia ada dalam buku tekanan darah anda.",
        ),
        "story_paper": (
            "{test_name} anda dari {day} ada dalam surat-surat anda.",
            "Anda boleh tunjukkan kepada {doctor} bila-bila masa.",
        ),
        "story_note": ("Pada {day} anda menulis begini:",),
        "story_count": (
            "Anda sudah tulis tekanan darah anda {count} kali.",
            "Nombor ini hanya naik.",
        ),
        "learning_source": ("Ini datang dari {source_name}.",),
        "flag_family": (
            "Anda beritahu Nura tentang {feeling}.",
            "Yang ini kita tidak tunggu.",
            "{who} sudah tahu.",
            "Telefon {who}, atau telefon {emergency_number}.",
        ),
        "flag_alone": (
            "Anda beritahu Nura tentang {feeling}.",
            "Yang ini kita tidak tunggu.",
            "Telefon {emergency_number} sekarang.",
        ),
    },
    "zh": {
        "now_tablets": (
            "您今天的药在您的清单上。",
            "请按照药盒上写的吃。",
            "吃了以后，请按“已吃”。",
        ),
        "now_tablets_voice": (
            "您今天的药在您的清单上。",
            "请按照药盒上写的吃。",
            "吃了以后，请按“已吃”。",
        ),
        "now_visit": ("您今天见{doctor}。", "请带上您的血压本和您的药。"),
        "now_quiet": ("今天没有新的事情等着您。", "想多听的时候，请向上滑。"),
        "reading": ("您今天的血压是{top_number}比{bottom_number}。", "它记在您的血压本里。"),
        "reading_family": ("{who}也能看到。",),
        "reading_alone": ("我已经记下了。",),
        "visit": ("您{day}见{doctor}。", "请带上您的血压本和您的药。"),
        "memo": ("上次看病时{doctor}这样说：",),
        "gate": ("今天新的就这些了。", "您想继续吗？", "向上滑，多听听关于您的事。"),
        "story_reading": ("{day}您的血压是{top_number}比{bottom_number}。", "它记在您的血压本里。"),
        "story_paper": ("您{day}的{test_name}在您的文件里。", "您随时可以拿给{doctor}看。"),
        "story_note": ("{day}您写下了这句话：",),
        "story_count": ("您已经记了{count}次血压。", "这个数字只会往上走。"),
        "learning_source": ("这来自{source_name}。",),
        "flag_family": (
            "您告诉Nura您{feeling}。",
            "这个我们不等。",
            "{who}已经知道了。",
            "请打给{who}，或者打{emergency_number}。",
        ),
        "flag_alone": ("您告诉Nura您{feeling}。", "这个我们不等。", "请现在打{emergency_number}。"),
    },
}

# @patient
WHY: Mapping[str, Mapping[str, str]] = {
    "en": {
        "now_tablets": "You have medicines on your list.",
        "now_visit": "Your visit to {doctor} is today.",
        "now_quiet": "There is nothing new on your papers today.",
        "reading": "You took your blood pressure today.",
        "visit": "Your visit to {doctor} is on {day}.",
        "memo": "You saw {doctor} on {day}.",
        "reorder": "You have about {days} days of {medicine} left.",
        "gate": "You have seen everything new for today.",
        "story_reading": "This is from your own blood pressure book.",
        "story_paper": "This is one of your own papers.",
        "story_note": "These are your own words, from your private notes.",
        "story_count": "This counts the days you took your blood pressure.",
        "learning": "This is about {topic}, which is on your papers.",
        "flag": "This is one of the things we never wait for.",
    },
    "ms": {
        "now_tablets": "Anda ada ubat dalam senarai anda.",
        "now_visit": "Lawatan anda kepada {doctor} hari ini.",
        "now_quiet": "Tiada yang baru dalam surat-surat anda hari ini.",
        "reading": "Anda ambil tekanan darah anda hari ini.",
        "visit": "Lawatan anda kepada {doctor} pada {day}.",
        "memo": "Anda berjumpa {doctor} pada {day}.",
        "reorder": "{medicine} anda tinggal lebih kurang {days} hari lagi.",
        "gate": "Anda sudah lihat semua yang baru hari ini.",
        "story_reading": "Ini dari buku tekanan darah anda sendiri.",
        "story_paper": "Ini salah satu surat anda sendiri.",
        "story_note": "Ini kata-kata anda sendiri, dari nota peribadi anda.",
        "story_count": "Ini mengira hari anda ambil tekanan darah.",
        "learning": "Ini tentang {topic}, yang ada dalam surat-surat anda.",
        "flag": "Ini salah satu perkara yang kita tidak pernah tunggu.",
    },
    "zh": {
        "now_tablets": "您的清单上有药。",
        "now_visit": "您今天要见{doctor}。",
        "now_quiet": "您的文件里今天没有新的东西。",
        "reading": "您今天量了血压。",
        "visit": "您{day}要见{doctor}。",
        "memo": "您{day}见了{doctor}。",
        "reorder": "{medicine}大概还够{days}天。",
        "gate": "今天新的您都看过了。",
        "story_reading": "这来自您自己的血压本。",
        "story_paper": "这是您自己的一份文件。",
        "story_note": "这是您自己的话，来自您的私人笔记。",
        "story_count": "这是在数您量血压的天数。",
        "learning": "这是关于{topic}的，它在您的文件里。",
        "flag": "这是我们从不等的事情之一。",
    },
}

# @patient phrase
FEELINGS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "fall": "a fall",
        "chest_tightness": "a tight chest",
        "breathless_at_rest": "being short of breath while resting",
        "one_sided_swelling": "one leg swelling",
        "worst_headache": "the worst headache of your life",
        "sudden_blurring": "sudden blurry eyes",
        "confusion": "feeling muddled",
        "shaky_sweaty": "feeling shaky and sweaty",
        "weight_gain": "putting on weight fast",
        "dizzy": "feeling dizzy",
        "cramps": "cramps",
        "thirsty": "feeling thirsty",
        "tired": "feeling tired",
        "aches": "muscle aches",
        "headache": "a headache",
        "pain": "pain",
        "breathless": "being short of breath",
        "low": "feeling low",
        "worried": "feeling worried",
        "cant_sleep": "poor sleep",
        "swollen_ankles": "swollen ankles",
        "stomach_upset": "an upset stomach",
        "fine": "feeling fine",
    },
    "ms": {
        "fall": "terjatuh",
        "chest_tightness": "dada rasa ketat",
        "breathless_at_rest": "sesak nafas semasa berehat",
        "one_sided_swelling": "sebelah kaki bengkak",
        "worst_headache": "sakit kepala paling teruk dalam hidup anda",
        "sudden_blurring": "mata tiba-tiba kabur",
        "confusion": "rasa keliru",
        "shaky_sweaty": "rasa menggigil dan berpeluh",
        "weight_gain": "berat naik dengan cepat",
        "dizzy": "rasa pening",
        "cramps": "kekejangan",
        "thirsty": "rasa dahaga",
        "tired": "rasa letih",
        "aches": "sakit otot",
        "headache": "sakit kepala",
        "pain": "rasa sakit",
        "breathless": "sesak nafas",
        "low": "rasa sedih",
        "worried": "rasa risau",
        "cant_sleep": "susah tidur",
        "swollen_ankles": "buku lali bengkak",
        "stomach_upset": "perut tidak selesa",
        "fine": "rasa sihat",
    },
    "zh": {
        "fall": "跌倒了",
        "chest_tightness": "胸口发紧",
        "breathless_at_rest": "休息时也喘不上气",
        "one_sided_swelling": "一条腿肿了",
        "worst_headache": "这辈子最痛的头痛",
        "sudden_blurring": "眼睛突然模糊",
        "confusion": "觉得糊涂",
        "shaky_sweaty": "发抖又出汗",
        "weight_gain": "体重涨得很快",
        "dizzy": "头晕",
        "cramps": "抽筋",
        "thirsty": "口渴",
        "tired": "累",
        "aches": "肌肉酸痛",
        "headache": "头痛",
        "pain": "痛",
        "breathless": "气短",
        "low": "心情低落",
        "worried": "担心",
        "cant_sleep": "睡不好",
        "swollen_ankles": "脚踝肿",
        "stomach_upset": "肚子不舒服",
        "fine": "还好",
    },
}

# @patient phrase
TEST_NAMES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "lipid_panel": "cholesterol test",
        "kidney_panel": "kidney test",
        "blood_test": "blood test",
        "medicine": "medicine label",
        "medication": "medicine label",
        "paper": "paper",
    },
    "ms": {
        "lipid_panel": "Ujian kolesterol",
        "kidney_panel": "Ujian buah pinggang",
        "blood_test": "Ujian darah",
        "medicine": "Label ubat",
        "medication": "Label ubat",
        "paper": "Surat",
    },
    "zh": {
        "lipid_panel": "胆固醇检查",
        "kidney_panel": "肾检查",
        "blood_test": "血检",
        "medicine": "药盒标签",
        "medication": "药盒标签",
        "paper": "文件",
    },
}

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}

EMERGENCY_NUMBER: Mapping[str, str] = {"SG": "995", "MY": "999"}
"""The ambulance number, by region: what a flag card says to call."""

DEFAULT_LANGUAGE = "en"
LANGUAGES: tuple[str, ...] = tuple(LINES)


def language_for(code: str | None) -> str:
    """The catalogue language for a profile language: its own, or English when the words
    for it are not on file yet (Tamil joins when its lines are here)."""
    return code if code is not None and code in LINES else DEFAULT_LANGUAGE


@dataclass(frozen=True, slots=True)
class Lines:
    """One card's words, filled: what he reads, what he hears, and why it is there."""

    language: str
    headline: str
    body: tuple[str, ...]
    voice: tuple[str, ...]
    why: str
    boundary: str | None = None
    """The boundary line a card of an inferring surface ends on (E16-01), as one string:
    the same words as the last lines of `body` and `voice`, kept whole so the row records
    it. None on a card that shows the record back and infers nothing."""


def _fill(template: str, slots: Mapping[str, Any]) -> str:
    return _sentence(template.format_map(slots))


def _sentence(line: str) -> str:
    """A line that begins with his name for a thing ("your blood pressure tablet runs out…")
    starts with a capital, as any line he reads does. Nothing else about it changes."""
    return line[:1].upper() + line[1:]


def render(
    kind: str,
    language: str | None,
    *,
    body: tuple[str, ...] = (),
    voice: tuple[str, ...] | None = None,
    why: str = "",
    headline: str = "",
    extra: tuple[str, ...] = (),
    **slots: Any,
) -> Lines:
    """Fill the templates for one card kind in one language.

    `kind` names the headline and the why; `body` names the line groups that make the body,
    in order (`"reading", "reading_family"`); `voice` the groups for the spoken twin, or the
    body again. `headline` and `why` name other keys when a card shares them. `extra` is
    lines written elsewhere and already verified there — a memo's, a note's, a compressed
    page's — appended after the templates; `create_item` verifies the whole card again.
    """
    code = language_for(language)
    heads, lines, whys = HEADLINES[code], LINES[code], WHY[code]
    tail = tuple(_sentence(line) for line in extra)
    body_lines = tuple(_fill(line, slots) for group in body for line in lines[group]) + tail
    spoken = body_lines
    if voice is not None:
        spoken = tuple(_fill(line, slots) for group in voice for line in lines[group]) + tail
    return Lines(
        language=code,
        headline=_fill(heads[headline or kind], slots),
        body=body_lines,
        voice=spoken,
        why=_fill(whys[why or kind], slots),
    )


def learning_lines(
    language: str | None,
    *,
    headline: str,
    body: tuple[str, ...],
    topic: str,
    source_name: str,
    doctor: str,
) -> Lines:
    """A learning card: the compressed lines, then where they came from, then the boundary
    line every inferring card carries, then why it is here.

    The boundary is `app.safety.boundary`'s line for the learning-card surface (E16-01) —
    what Nura did, "This is not a doctor's advice.", "Ask {doctor}." — the same words as on
    every inferring surface, never a copy of them kept here. It ends the body and the voice
    and rides on `Lines.boundary`, so `items.create_item` writes it on the row."""
    code = language_for(language)
    slots = {"source_name": source_name, "doctor": doctor, "topic": topic}
    source = tuple(_fill(line, slots) for line in LINES[code]["learning_source"])
    boundary = boundary_line(Surface.LEARNING_CARD, code, doctor=doctor)
    lines = (*body, *source, *boundary.splitlines())
    return Lines(
        language=code,
        headline=headline,
        body=lines,
        voice=lines,
        why=_fill(WHY[code]["learning"], slots),
        boundary=boundary,
    )


def feeling_words(word: str, language: str | None) -> str:
    """His words for one feeling, from the cloud."""
    return FEELINGS[language_for(language)][word]


def test_name(subject: str, language: str | None) -> str:
    """His words for the kind of paper a fact came from."""
    names = TEST_NAMES[language_for(language)]
    return names[subject] if subject in names else names["paper"]


# --- the caregiver's lines -----------------------------------------------------------------
# Not patient strings: the caregiver's screens keep the fuller words (docs/plain-words.md §3).

CAREGIVER_DUTY_HEADLINE = "Who is on duty"
CAREGIVER_DUTY_LINES = ("{count} people hold a key to {name}'s record today.",)
CAREGIVER_NO_ROSTER_LINE = "Nobody is on the roster for now; add a slot under Family."
CAREGIVER_ON_DUTY_LINE = "{who} is on duty for {name} right now, by the roster."
CAREGIVER_DUTY_WHY = "Who holds a key is in the family dimension of State."
CAREGIVER_ROSTER_WHY = "The roster says who is on duty now; the keys say who else can step in."
CAREGIVER_HELD_WHY = "Held for you: nothing for {name} to do, or a question for the doctor."
CAREGIVER_SUPPRESSED_HEADLINE = "Considered, not raised: {feeling}"
CAREGIVER_SUPPRESSED_LINE = (
    "{name} said {feeling}. This flag depends on a fact that is not on the record ({reason}), "
    "so it was not raised to him. Add the fact, or ask the doctor."
)

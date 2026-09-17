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

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
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
        "logistics_today": "Getting to {doctor} today",
        "logistics_tomorrow": "Getting to {doctor} tomorrow",
        "memo": "What {doctor} said",
        "reorder": "{medicine} is running low",
        "recall_action": "{medicine} was recalled",
        "gate": "That is all that is new",
        "story_reading": "From your blood pressure book",
        "story_paper": "From your papers",
        "story_note": "Your own words",
        "story_count": "The number that only goes up",
        "story_change": "How your blood pressure moved",
        "story_trend": "Your blood test over time",
        "story_photo": "A photo from {who}",
        "recap": "Your week, in 30 seconds",
        "flag": "This one we do not wait for",
        "needs_doctor_look": "Nura kept this for {doctor}",
    },
    "ms": {
        "now_tablets": "Ubat anda hari ini",
        "now_visit": "Anda berjumpa {doctor} hari ini",
        "now_quiet": "Hari yang tenang",
        "reading": "Tekanan darah anda hari ini",
        "visit": "{doctor} pada {day}",
        "logistics_today": "Pergi jumpa {doctor} hari ini",
        "logistics_tomorrow": "Pergi jumpa {doctor} esok",
        "memo": "Apa yang {doctor} kata",
        "reorder": "{medicine} hampir habis",
        "recall_action": "{medicine} ditarik balik",
        "gate": "Itu sahaja yang baru",
        "story_reading": "Dari buku tekanan darah anda",
        "story_paper": "Dari surat-surat anda",
        "story_note": "Kata-kata anda sendiri",
        "story_count": "Nombor yang hanya naik",
        "story_change": "Bagaimana tekanan darah anda berubah",
        "story_trend": "Ujian darah anda dari masa ke masa",
        "story_photo": "Gambar daripada {who}",
        "recap": "Minggu anda, dalam 30 saat",
        "flag": "Yang ini kita tidak tunggu",
        "needs_doctor_look": "Nura simpan ini untuk {doctor}",
    },
    "zh": {
        "now_tablets": "您今天的药",
        "now_visit": "您今天看{doctor}",
        "now_quiet": "平静的一天",
        "reading": "您今天的血压",
        "visit": "{day}看{doctor}",
        "logistics_today": "今天去看{doctor}",
        "logistics_tomorrow": "明天去看{doctor}",
        "memo": "{doctor}说的话",
        "reorder": "您的{medicine}快用完了",
        "recall_action": "{medicine}被召回了",
        "gate": "新的就这些了",
        "story_reading": "来自您的血压本",
        "story_paper": "来自您的文件",
        "story_note": "您自己的话",
        "story_count": "只会往上走的数字",
        "story_change": "您的血压有什么变化",
        "story_trend": "您的验血结果",
        "story_photo": "{who}分享的照片",
        "recap": "30秒看您的这一周",
        "flag": "这个我们不等",
        "needs_doctor_look": "Nura 为{doctor}留下了这个",
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
            "You have taken your tablets on {count} days.",
            "This number only goes up.",
        ),
        "story_count_one": (
            "You have taken your tablets on 1 day.",
            "This number only goes up.",
        ),
        "story_change": ("On {day} your blood pressure was {top_number} over {bottom_number}.",),
        "story_change_before": ("On {day} it was {top_number} over {bottom_number}.",),
        "story_up": ("The top number went up.",),
        "story_down": ("The top number went down.",),
        "story_same": ("The top number stayed the same.",),
        "story_doctor": ("At your visit on {day}, {doctor} said this:",),
        "story_photo": ("{who} shared this photo on {day}.",),
        "learning_source": ("This comes from {source_name}.",),
        # A card about one of his medicines never reads as a reason to stop it. Worded without
        # naming the medicine beside "stop" (#236): `changes_treatment` reads any line pairing
        # a stop/start/change verb with a drug word as advice to act on it, and this line — a
        # caution against acting without asking — is the opposite of that, not a false one of
        # its own kind.
        "learning_keep_taking": ("Ask {doctor} before you stop taking it.",),
        # His own pack matched a recall (#183): what he can act on, not the notice's own
        # words about the recall — those are never his to read (spec §0, §2).
        "recall_action": (
            "Take {medicine} to the pharmacist today.",
            "The pharmacist will tell you what to do next.",
        ),
        "recap_intro": ("This is your week, from your blood pressure book.",),
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
        # #236: a finding whose words would start, stop or change a medicine is never
        # addressed to the caregiver in its own words — a fixed line reaches her instead,
        # naming that a question is already filed for the doctor, never the finding itself.
        "needs_doctor_look": (
            "Nura found something that needs {doctor}'s look.",
            "Nura already saved a question for {doctor}.",
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
        "reading_alone": ("Saya sudah tulis.",),
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
            "Anda sudah ambil ubat anda pada {count} hari.",
            "Nombor ini hanya naik.",
        ),
        "story_count_one": (
            "Anda sudah ambil ubat anda pada 1 hari.",
            "Nombor ini hanya naik.",
        ),
        "story_change": ("Pada {day} tekanan darah anda {top_number} atas {bottom_number}.",),
        "story_change_before": ("Pada {day} ia {top_number} atas {bottom_number}.",),
        "story_up": ("Nombor atas sudah naik.",),
        "story_down": ("Nombor atas sudah turun.",),
        "story_same": ("Nombor atas masih sama.",),
        "story_doctor": ("Semasa lawatan anda pada {day}, {doctor} kata begini:",),
        "story_photo": ("{who} berkongsi gambar ini pada {day}.",),
        "learning_source": ("Ini datang dari {source_name}.",),
        "learning_keep_taking": ("Tanya {doctor} sebelum anda berhenti mengambilnya.",),
        "recall_action": (
            "Bawa {medicine} kepada ahli farmasi hari ini.",
            "Ahli farmasi akan beritahu anda apa yang perlu dibuat seterusnya.",
        ),
        "recap_intro": ("Ini minggu anda, dari buku tekanan darah anda.",),
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
        "needs_doctor_look": (
            "Nura jumpa sesuatu yang perlu dilihat {doctor}.",
            "Nura sudah simpan soalan untuk {doctor}.",
        ),
    },
    "zh": {
        "now_tablets": (
            "您今天的药在您的清单上。",
            "请按照药盒上写的吃。",
            "吃了以后，请按“吃了”。",
        ),
        "now_tablets_voice": (
            "您今天的药在您的清单上。",
            "请按照药盒上写的吃。",
            "吃了以后，请按“吃了”。",
        ),
        "now_visit": ("您今天看{doctor}。", "请带上您的血压本和您的药。"),
        "now_quiet": ("今天没有新的事情等着您。", "想多听的时候，请向上滑。"),
        "reading": ("您今天的血压是{top_number}比{bottom_number}。", "它记在您的血压本里。"),
        "reading_family": ("{who}也能看到。",),
        "reading_alone": ("我记下了。",),
        "visit": ("您{day}看{doctor}。", "请带上您的血压本和您的药。"),
        "memo": ("上次看病时{doctor}这样说：",),
        "gate": ("今天新的就这些了。", "您想继续吗？", "向上滑，多听听关于您的事。"),
        "story_reading": ("{day}您的血压是{top_number}比{bottom_number}。", "它记在您的血压本里。"),
        "story_paper": ("您{day}的{test_name}在您的文件里。", "您随时可以拿给{doctor}看。"),
        "story_note": ("{day}您写下了这句话：",),
        "story_count": ("您已经有 {count} 天吃了药。", "这个数字只会往上走。"),
        "story_count_one": ("您已经有 1 天吃了药。", "这个数字只会往上走。"),
        "story_change": ("{day}您的血压是{top_number}比{bottom_number}。",),
        "story_change_before": ("{day}是{top_number}比{bottom_number}。",),
        "story_up": ("上面的数字升高了。",),
        "story_down": ("上面的数字降低了。",),
        "story_same": ("上面的数字没有变。",),
        "story_doctor": ("{day}看病时{doctor}这样说：",),
        "story_photo": ("{who}在{day}分享了这张照片。",),
        "learning_source": ("这来自{source_name}。",),
        "learning_keep_taking": ("停用它以前，先问一问{doctor}。",),
        "recall_action": ("今天把{medicine}带去给药剂师。", "药剂师会告诉您接下来要怎么做。"),
        "recap_intro": ("这些是您这一周的血压，来自您的血压本。",),
        "flag_family": (
            "您告诉Nura您{feeling}。",
            "这个我们不等。",
            "{who}已经知道了。",
            "请打给{who}，或者打{emergency_number}。",
        ),
        "flag_alone": ("您告诉Nura您{feeling}。", "这个我们不等。", "请现在打{emergency_number}。"),
        "needs_doctor_look": ("Nura 发现了需要{doctor}查看的事。", "Nura 已经给{doctor}留了一个问题。"),
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
        "visit_logistics": "Your visit to {doctor} is on {day}.",
        "memo": "You saw {doctor} on {day}.",
        "reorder": "You have about {days} days of {medicine} left.",
        "reorder_one": "You have about 1 day of {medicine} left.",
        "recall_action": "{medicine} was named in a safety notice.",
        "gate": "You have seen everything new for today.",
        "story_reading": "This is from your own blood pressure book.",
        "story_paper": "This is one of your own papers.",
        "story_note": "These are your own words, from your private notes.",
        "story_count": "Nura counted the days you took your tablets.",
        "story_trend": "This is from your own blood tests.",
        "story_photo": "{who} chose to share this photo with you.",
        "learning": "This is about {topic}, which is on your papers.",
        "local": "You are seeing this because it is near your home.",
        "local_region": "You are seeing this because of what is on your papers.",
        "seasonal": "{season} is on {day}.",
        "seasonal_about": "{season} begins around {day}.",
        "flag": "This is one of the things we never wait for.",
        "needs_doctor_look": "Nura found something to ask {doctor} about.",
        "withheld": "Part of your papers is not shown here.",
    },
    "ms": {
        "now_tablets": "Anda ada ubat dalam senarai anda.",
        "now_visit": "Lawatan anda kepada {doctor} hari ini.",
        "now_quiet": "Tiada yang baru dalam surat-surat anda hari ini.",
        "reading": "Anda ambil tekanan darah anda hari ini.",
        "visit": "Lawatan anda kepada {doctor} pada {day}.",
        "visit_logistics": "Lawatan anda kepada {doctor} pada {day}.",
        "memo": "Anda berjumpa {doctor} pada {day}.",
        "reorder": "{medicine} anda tinggal lebih kurang {days} hari lagi.",
        "reorder_one": "{medicine} anda tinggal lebih kurang 1 hari lagi.",
        "recall_action": "{medicine} disebut dalam satu notis keselamatan.",
        "gate": "Anda sudah lihat semua yang baru hari ini.",
        "story_reading": "Ini dari buku tekanan darah anda sendiri.",
        "story_paper": "Ini salah satu surat anda sendiri.",
        "story_note": "Ini kata-kata anda sendiri, dari nota peribadi anda.",
        "story_count": "Nura mengira hari anda ambil ubat anda.",
        "story_trend": "Ini dari ujian darah anda sendiri.",
        "story_photo": "{who} memilih untuk berkongsi gambar ini dengan anda.",
        "learning": "Ini tentang {topic}, yang ada dalam surat-surat anda.",
        "local": "Anda nampak ini kerana ia dekat rumah anda.",
        "local_region": "Anda nampak ini kerana apa yang ada dalam surat-surat anda.",
        "seasonal": "{season} jatuh pada {day}.",
        "seasonal_about": "{season} bermula sekitar {day}.",
        "flag": "Ini salah satu perkara yang kita tidak pernah tunggu.",
        "needs_doctor_look": "Nura jumpa sesuatu untuk ditanya kepada {doctor}.",
        "withheld": "Sebahagian surat anda tidak ditunjukkan di sini.",
    },
    "zh": {
        "now_tablets": "您的清单上有药。",
        "now_visit": "您今天要看{doctor}。",
        "now_quiet": "您的文件里今天没有新的东西。",
        "reading": "您今天量了血压。",
        "visit": "您{day}要看{doctor}。",
        "visit_logistics": "您{day}要看{doctor}。",
        "memo": "您{day}看了{doctor}。",
        "reorder": "{medicine}大概还够{days}天。",
        "reorder_one": "{medicine}大概还够1天。",
        "recall_action": "一个安全通知提到了{medicine}。",
        "gate": "今天新的您都看过了。",
        "story_reading": "这来自您自己的血压本。",
        "story_paper": "这是您自己的一份文件。",
        "story_note": "这是您自己的话，来自您的私人笔记。",
        "story_count": "Nura 数了您吃药的天数。",
        "story_trend": "这来自您自己的验血结果。",
        "story_photo": "{who}选择了和您分享这张照片。",
        "learning": "这是关于{topic}的，它在您的文件里。",
        "local": "您看到这个，是因为这在您家附近。",
        "local_region": "您看到这个，是因为您文件里的情况。",
        "seasonal": "{season}是{day}。",
        "seasonal_about": "{season}大约在{day}开始。",
        "flag": "这是我们从不等的事情之一。",
        "needs_doctor_look": "Nura 发现了需要问{doctor}的事。",
        "withheld": "您的文件有一部分不会显示在这里。",
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
        "low": "feeling sad",
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
        "blood_test": "验血",
        "medicine": "药盒标签",
        "medication": "药盒标签",
        "paper": "文件",
    },
}

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}

# @patient
FIND_STEPS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "web": "Looking online.",
        "videos": "Looking for videos.",
    },
    "ms": {
        "web": "Melihat di web.",
        "videos": "Melihat video.",
    },
    "zh": {
        "web": "正在网上查看。",
        "videos": "正在查看视频。",
    },
}
"""What the ask bar's Web and Videos filters say while the allowlisted search runs
(`app.delivery.feed.find.find_stream`, docs/design-direction.md 'Conversation, waiting and
thinking'). One step, said once, because there is one real stage before the results: the
search itself. Providers is a directory read and streams nothing."""

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


def counted(key: str, count: int) -> str:
    """The template for this many: `<key>_one` for exactly one, else `<key>`. A count agrees
    with its noun in every line — "1 time", "1 day", never "1 times" — and each language
    carries both forms (Malay and Chinese say them alike), so a line is looked up, never
    patched at run time."""
    return f"{key}_one" if count == 1 else key


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
    why: str = "learning",
    keep_taking: bool = False,
    **slots: Any,
) -> Lines:
    """A learning card: the compressed lines, then where they came from, then the boundary
    line every inferring card carries, then why it is here. A card about one of his medicines
    (`keep_taking`) says, after its lines, not to stop it without asking his doctor: a line
    about what a medicine can do is never read as a reason to stop it.

    The boundary is `app.safety.boundary`'s line for the learning-card surface (E16-01) —
    what Nura did, "This is not a doctor's advice.", "Ask {doctor}." — the same words as on
    every inferring surface, never a copy of them kept here. It ends the body and the voice
    and rides on `Lines.boundary`, so `items.create_item` writes it on the row."""
    code = language_for(language)
    filled = {"source_name": source_name, "doctor": doctor, "topic": topic, **slots}
    source = tuple(_fill(line, filled) for line in LINES[code]["learning_source"])
    boundary = boundary_line(Surface.LEARNING_CARD, code, doctor=doctor)
    keep = tuple(_fill(line, filled) for line in LINES[code]["learning_keep_taking"]) if keep_taking else ()
    lines = (*body, *keep, *source, *boundary.splitlines())
    return Lines(
        language=code,
        headline=headline,
        body=lines,
        voice=lines,
        why=_fill(WHY[code][why], filled),
        boundary=boundary,
    )


def recall_action_lines(language: str | None, *, medicine: str, doctor: str) -> Lines:
    """His own card for the one case a safety notice needs him at all (#183): his own pack is
    one of the recalled batches. In his own words, from the catalogue, like every other card
    of his — never the notice's own compressed words about the recall, which stay
    `learning_lines`' and are his chief's alone. It says what is true (`{medicine}` was
    recalled) and who to ask today (the pharmacist), never that he should stop taking it: no
    line here or in `LINES[*]["recall_action"]` may say to start, stop or change a medicine.

    Ends on the same boundary line a learning card carries (`Surface.LEARNING_CARD`,
    E16-01): this card exists because State surfaced a regulator's notice, even though its
    own words never do."""
    code = language_for(language)
    filled = {"medicine": medicine, "doctor": doctor}
    body = tuple(_fill(line, filled) for line in LINES[code]["recall_action"])
    boundary = boundary_line(Surface.LEARNING_CARD, code, doctor=doctor)
    lines = (*body, *boundary.splitlines())
    return Lines(
        language=code,
        headline=_fill(HEADLINES[code]["recall_action"], filled),
        body=lines,
        voice=lines,
        why=_fill(WHY[code]["recall_action"], filled),
        boundary=boundary,
    )


def needs_doctor_look_lines(language: str | None, *, doctor: str) -> Lines:
    """The fixed line for a finding that would start, stop or change a medicine (#236): never
    the finding's own words — `items.create_item` refuses any card that carries them, for any
    audience — so the caregiver gets this instead: that something needs her doctor's look, and
    that a question is already filed for him (`search._ask_the_doctor`). This can never itself
    fail, because it never repeats what the finding said.

    Carries the same boundary line every inferring surface does (`Surface.LEARNING_CARD`),
    since the type this stands in for (`CardType.NOTICE`, or whatever `_shape` chose) still
    names that surface and `items.create_item` still requires it."""
    code = language_for(language)
    boundary = boundary_line(Surface.LEARNING_CARD, code, doctor=doctor)
    base = render("needs_doctor_look", code, body=("needs_doctor_look",), doctor=doctor)
    tail = boundary.splitlines()
    return replace(base, body=(*base.body, *tail), voice=(*base.voice, *tail), boundary=boundary)


# @patient phrase
SEASON_NAMES: Mapping[str, Mapping[str, str]] = {
    # "Fasting" is his word for no food before a blood test (the glossary), so in English the
    # month is its name.
    "en": {"mid_autumn": "The Mid-Autumn Festival", "fasting_month": "Ramadan"},
    "ms": {"mid_autumn": "Pesta Kuih Bulan", "fasting_month": "Bulan puasa"},
    "zh": {"mid_autumn": "中秋节", "fasting_month": "斋戒月"},
}
"""His words for a season, to fill the seasonal card's why line (`app.delivery.feed.local`),
which it begins, so each starts with a capital."""


def season_name(code: str, language: str | None) -> str:
    return SEASON_NAMES[language_for(language)][code]


# @patient phrase
TERM_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood pressure": "blood pressure",
        "diabetes": "diabetes",
        "cholesterol": "cholesterol",
        "heart": "the heart",
        "kidneys": "the kidneys",
        "dengue": "dengue",
        "haze": "the haze",
        "heat": "hot weather",
        "festive food": "festive food",
        "fasting month": "Ramadan",
    },
    "ms": {
        "blood pressure": "tekanan darah",
        "diabetes": "kencing manis",
        "cholesterol": "kolesterol",
        "heart": "jantung",
        "kidneys": "buah pinggang",
        "dengue": "denggi",
        "haze": "jerebu",
        "heat": "cuaca panas",
        "festive food": "makanan perayaan",
        "fasting month": "bulan puasa",
    },
    "zh": {
        "blood pressure": "血压",
        "diabetes": "糖尿病",
        "cholesterol": "胆固醇",
        "heart": "心脏",
        "kidneys": "肾脏",
        "dengue": "骨痛热症",
        "haze": "烟霾",
        "heat": "炎热天气",
        "festive food": "节日食物",
        "fasting month": "斋戒月",
    },
}
"""A search term in the reader's words, for the "Watching for Pa" list. A medicine's generic
name is the same in every language and is shown as it is."""

AND: Mapping[str, str] = {"en": " and ", "ms": " dan ", "zh": "和"}


def term_words(terms: tuple[str, ...] | list[str], language: str | None) -> str:
    code = language_for(language)
    words = [TERM_WORDS[code].get(term, term) for term in terms]
    return AND[code].join(words)


# @patient headline
WATCH_LABELS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "explainer": "{term}, in simple words",
        "safety": "Safety notices about {term}",
        "local": "{term} near {area}",
        "local_region": "{term} anywhere in the country",
        "seasonal": "{term}, before it comes",
        "food": "Food choices for {term}",
        "provider": "News from {term}",
        "worth_knowing": "Worth asking about {term}",
    },
    "ms": {
        "explainer": "{term}, dalam kata-kata mudah",
        "safety": "Notis keselamatan tentang {term}",
        "local": "{term} dekat {area}",
        "local_region": "{term} di seluruh negara",
        "seasonal": "{term}, sebelum tiba",
        "food": "Pilihan makanan untuk {term}",
        "provider": "Berita dari {term}",
        "worth_knowing": "Patut ditanya tentang {term}",
    },
    "zh": {
        "explainer": "用简单的话讲{term}",
        "safety": "关于{term}的安全通知",
        "local": "{area}附近的{term}",
        "local_region": "全国各地的{term}",
        "seasonal": "{term}来临前的提醒",
        "food": "适合{term}的食物选择",
        "provider": "来自{term}的消息",
        "worth_knowing": "值得问的：{term}",
    },
}
"""What one search job watches for, in the caregiver's words ("Watching for Pa", spec §1)."""


def watch_label(kind: str, terms: list[str], language: str | None, area: str | None) -> str:
    """What one watch is for, as a line that starts with a capital ("Dengue near Air Itam")."""
    code = language_for(language)
    key = "local_region" if kind == "local" and not area else kind
    line = _fill(WATCH_LABELS[code][key], {"term": term_words(terms, code), "area": area or ""})
    return line[:1].upper() + line[1:]


def feeling_words(word: str, language: str | None) -> str:
    """His words for one feeling, from the cloud."""
    return FEELINGS[language_for(language)][word]


def test_name(subject: str, language: str | None) -> str:
    """His words for the kind of paper a fact came from."""
    names = TEST_NAMES[language_for(language)]
    return names[subject] if subject in names else names["paper"]


# @patient
PUSH_LINE: Mapping[str, str] = {
    "en": "Nura has something for you.",
    "ms": "Nura ada sesuatu untuk anda.",
    "zh": "Nura 有东西给您。",
}
"""The whole of an app push (E11-05): no health content rides through a phone maker's
servers; the app opens and reads the card from the region."""


def theirs(medicine: str, name: str, language: str | None) -> str:
    """His words for a medicine, said about him to someone else: "your blood pressure tablet"
    to him is "Pa's blood pressure tablet" to Siti. Only the possessive changes, wherever it
    sits ("ubat tekanan darah anda (amlodipine)" is "ubat tekanan darah Pa (amlodipine)")."""
    code = language_for(language)
    if code == "en":
        return re.sub(r"\byour\b", f"{name}'s", medicine, flags=re.IGNORECASE)
    if code == "ms":
        return re.sub(r"\banda\b", name, medicine, flags=re.IGNORECASE)
    return medicine.replace("您的", f"{name}的").replace("您", name)


# --- the caregiver's lines -----------------------------------------------------------------
# Not patient strings: the caregiver's screens keep the fuller words (docs/plain-words.md §3).

CAREGIVER_DUTY_HEADLINE = "Who is on duty"
CAREGIVER_DUTY_LINES = ("{count} people hold a key to {name}'s record today.",)
CAREGIVER_DUTY_LINES_ONE = ("1 person holds a key to {name}'s record today.",)
CAREGIVER_NO_ROSTER_LINE = "Nobody is on the roster for now; add a slot under Family."
CAREGIVER_ON_DUTY_LINE = "{who} is on duty for {name} right now, by the roster."
CAREGIVER_DUTY_WHY = "Who holds a key is in the family dimension of State."
CAREGIVER_ROSTER_WHY = "The roster says who is on duty now; the keys say who else can step in."
CAREGIVER_HELD_WHY = "Held for you: nothing for {name} to do, or a question for the doctor."
CAREGIVER_SUPPRESSED_HEADLINE = "Considered, not raised: {feeling}"
CAREGIVER_HEARD_HEADLINE = "Heard at the visit: {word}"
CAREGIVER_HEARD_LINE = (
    'The words "{word}" were heard in the transcript of {name}\'s visit. '
    "His summary card tells him to call his doctor today."
)
CAREGIVER_SUPPRESSED_LINE = (
    "{name} said {feeling}. This flag depends on a fact that is not on the record ({reason}), "
    "so it was not raised to him. Add the fact, or ask the doctor."
)

# --- about him, to someone else (D1) ------------------------------------------------------------
# The same cards, said about him by name to a family member reading his papers with her own key:
# each twin mirrors its original's keys and places, "{patient}" his name as the family writes it.
# Chosen on the backend for a key that is not his (`app.channels.about_him`); a line with no twin
# that speaks to him is not shown to anyone else.

# @patient headline
HEADLINES_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "recap": "{patient}'s week, in 30 seconds",
        "now_tablets": "{patient}'s tablets today",
        "now_visit": "{patient} sees {doctor} today",
        "reading": "{patient}'s blood pressure today",
        "story_reading": "From {patient}'s blood pressure book",
        "story_paper": "From {patient}'s papers",
        "story_note": "{patient}'s own words",
        "story_change": "How {patient}'s blood pressure moved",
        "story_trend": "{patient}'s blood test over time",
        "needs_doctor_look": "Nura kept this about {patient} for {doctor}",
        "recall_action": "{patient}'s {medicine} was recalled",
    },
    "ms": {
        "recap": "Minggu {patient}, dalam 30 saat",
        "now_tablets": "Ubat {patient} hari ini",
        "now_visit": "{patient} berjumpa {doctor} hari ini",
        "reading": "Tekanan darah {patient} hari ini",
        "story_reading": "Dari buku tekanan darah {patient}",
        "story_paper": "Dari surat-surat {patient}",
        "story_note": "Kata-kata {patient} sendiri",
        "story_change": "Bagaimana tekanan darah {patient} berubah",
        "story_trend": "Ujian darah {patient} dari masa ke masa",
        "needs_doctor_look": "Nura simpan ini tentang {patient} untuk {doctor}",
        "recall_action": "{medicine} {patient} ditarik balik",
    },
    "zh": {
        "recap": "30秒看{patient}的这一周",
        "now_tablets": "{patient}今天的药",
        "now_visit": "{patient}今天看{doctor}",
        "reading": "{patient}今天的血压",
        "story_reading": "来自{patient}的血压本",
        "story_paper": "来自{patient}的文件",
        "story_note": "{patient}自己的话",
        "story_change": "{patient}的血压有什么变化",
        "story_trend": "{patient}的验血结果",
        "needs_doctor_look": "Nura 为{doctor}留下了关于{patient}的这个",
        "recall_action": "{patient}的{medicine}被召回了",
    },
}
"""A card's headline said about him by name."""

# @patient
LINES_THEIRS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "en": {
        "now_quiet": ("Nothing new is waiting for {patient} today.", "Swipe up to hear more."),
        "gate": ("That is all that is new today.", "Do you want to keep going?", "Swipe up to hear more about {patient}."),
        "learning_keep_taking": ("Ask {doctor} before {patient} stops taking it.",),
        "recap_intro": ("This is {patient}'s week, from {patient}'s blood pressure book.",),
        "now_tablets": (
            "{patient}'s tablets for today are on the list.",
            "{patient} takes them the way the label says.",
            "Tap when {patient} has had them.",
        ),
        "now_visit": (
            "{patient} sees {doctor} today.",
            "Bring {patient}'s blood pressure book and tablets.",
        ),
        "reading": (
            "{patient}'s blood pressure today was {top_number} over {bottom_number}.",
            "It is in {patient}'s blood pressure book.",
        ),
        "visit": (
            "{patient} sees {doctor} on {day}.",
            "Bring {patient}'s blood pressure book and tablets.",
        ),
        "memo": ("At {patient}'s last visit {doctor} said this:",),
        "story_reading": (
            "On {day} {patient}'s blood pressure was {top_number} over {bottom_number}.",
            "It is in {patient}'s blood pressure book.",
        ),
        "story_paper": (
            "{patient}'s {test_name} from {day} is in the papers.",
            "{patient} can show it to {doctor} any time.",
        ),
        "story_note": ("On {day} {patient} wrote this down:",),
        "story_count": (
            "{patient} has taken the tablets on {count} days.",
            "This number only goes up.",
        ),
        "story_count_one": (
            "{patient} has taken the tablets on 1 day.",
            "This number only goes up.",
        ),
        "story_change": (
            "On {day} {patient}'s blood pressure was {top_number} over {bottom_number}.",
        ),
        "story_doctor": ("At {patient}'s visit on {day}, {doctor} said this:",),
        "flag_family": (
            "{patient} told Nura about {feeling}.",
            "This one we do not wait for.",
            "{who} knows now.",
            "Call {who}, or call {emergency_number}.",
        ),
        "flag_alone": (
            "{patient} told Nura about {feeling}.",
            "This one we do not wait for.",
            "Call {emergency_number} now.",
        ),
        "needs_doctor_look": (
            "Nura found something about {patient} that needs {doctor}'s look.",
            "Nura already saved a question for {doctor}.",
        ),
        "recall_action": (
            "Take {patient}'s {medicine} to the pharmacist today.",
            "The pharmacist will tell {patient} what to do next.",
        ),
    },
    "ms": {
        "now_quiet": ("Tiada yang baru menunggu {patient} hari ini.", "Leret ke atas untuk dengar lagi."),
        "gate": ("Itu sahaja yang baru hari ini.", "Mahu terus?", "Leret ke atas untuk dengar lagi tentang {patient}."),
        "learning_keep_taking": ("Tanya {doctor} sebelum {patient} berhenti mengambilnya.",),
        "recap_intro": ("Ini minggu {patient}, dari buku tekanan darah {patient}.",),
        "now_tablets": (
            "Ubat {patient} untuk hari ini ada dalam senarai.",
            "{patient} ambil ikut apa yang tertulis pada label.",
            "Tekan apabila {patient} sudah makan ubat.",
        ),
        "now_visit": (
            "{patient} berjumpa {doctor} hari ini.",
            "Bawa buku tekanan darah dan ubat {patient}.",
        ),
        "reading": (
            "Tekanan darah {patient} hari ini {top_number} atas {bottom_number}.",
            "Ia ada dalam buku tekanan darah {patient}.",
        ),
        "visit": (
            "{patient} berjumpa {doctor} pada {day}.",
            "Bawa buku tekanan darah dan ubat {patient}.",
        ),
        "memo": ("Pada lawatan terakhir {patient}, {doctor} berkata begini:",),
        "story_reading": (
            "Pada {day} tekanan darah {patient} {top_number} atas {bottom_number}.",
            "Ia ada dalam buku tekanan darah {patient}.",
        ),
        "story_paper": (
            "{test_name} {patient} dari {day} ada dalam surat-surat.",
            "{patient} boleh tunjukkan kepada {doctor} bila-bila masa.",
        ),
        "story_note": ("Pada {day} {patient} menulis begini:",),
        "story_count": ("{patient} sudah ambil ubat pada {count} hari.", "Nombor ini hanya naik."),
        "story_count_one": ("{patient} sudah ambil ubat pada 1 hari.", "Nombor ini hanya naik."),
        "story_change": ("Pada {day} tekanan darah {patient} {top_number} atas {bottom_number}.",),
        "story_doctor": ("Semasa lawatan {patient} pada {day}, {doctor} kata begini:",),
        "flag_family": (
            "{patient} beritahu Nura tentang {feeling}.",
            "Yang ini kita tidak tunggu.",
            "{who} sudah tahu.",
            "Telefon {who}, atau telefon {emergency_number}.",
        ),
        "flag_alone": (
            "{patient} beritahu Nura tentang {feeling}.",
            "Yang ini kita tidak tunggu.",
            "Telefon {emergency_number} sekarang.",
        ),
        "needs_doctor_look": (
            "Nura jumpa sesuatu tentang {patient} yang perlu dilihat {doctor}.",
            "Nura sudah simpan soalan untuk {doctor}.",
        ),
        "recall_action": (
            "Bawa {medicine} {patient} kepada ahli farmasi hari ini.",
            "Ahli farmasi akan beritahu {patient} apa yang perlu dibuat seterusnya.",
        ),
    },
    "zh": {
        "now_quiet": ("今天没有新的事情等着{patient}。", "想多看的时候，请向上滑。"),
        "gate": ("今天新的就这些了。", "您想继续吗？", "向上滑，多看看关于{patient}的事。"),
        "learning_keep_taking": ("{patient}停用它以前，先问一问{doctor}。",),
        "recap_intro": ("这些是{patient}这一周的血压，来自{patient}的血压本。",),
        "now_tablets": (
            "{patient}今天的药在清单上。",
            "{patient}按照药盒上写的吃。",
            "{patient}吃了以后，请按一下。",
        ),
        "now_visit": ("{patient}今天看{doctor}。", "请带上{patient}的血压本和药。"),
        "reading": (
            "{patient}今天的血压是{top_number}比{bottom_number}。",
            "它记在{patient}的血压本里。",
        ),
        "visit": ("{patient}{day}看{doctor}。", "请带上{patient}的血压本和药。"),
        "memo": ("{patient}上次看病时{doctor}这样说：",),
        "story_reading": (
            "{day}{patient}的血压是{top_number}比{bottom_number}。",
            "它记在{patient}的血压本里。",
        ),
        "story_paper": (
            "{patient}{day}的{test_name}在文件里。",
            "{patient}随时可以拿给{doctor}看。",
        ),
        "story_note": ("{day}{patient}写下了这句话：",),
        "story_count": ("{patient}已经有 {count} 天吃了药。", "这个数字只会往上走。"),
        "story_count_one": ("{patient}已经有 1 天吃了药。", "这个数字只会往上走。"),
        "story_change": ("{day}{patient}的血压是{top_number}比{bottom_number}。",),
        "story_doctor": ("{patient}{day}看病时{doctor}这样说：",),
        "flag_family": (
            "{patient}告诉Nura自己{feeling}。",
            "这个我们不等。",
            "{who}已经知道了。",
            "请打给{who}，或者打{emergency_number}。",
        ),
        "flag_alone": (
            "{patient}告诉Nura自己{feeling}。",
            "这个我们不等。",
            "请现在打{emergency_number}。",
        ),
        "needs_doctor_look": (
            "Nura 发现了关于{patient}、需要{doctor}查看的事。",
            "Nura 已经给{doctor}留了一个问题。",
        ),
        "recall_action": ("今天把{patient}的{medicine}带去给药剂师。", "药剂师会告诉{patient}接下来要怎么做。"),
    },
}
"""A card's lines said about him by name, place for place with `LINES`."""

# @patient
WHY_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "gate": "Everything new for today has been seen.",
        "local": "This is here because it is near {patient}'s home.",
        "now_tablets": "{patient} has medicines on the list.",
        "now_visit": "{patient}'s visit to {doctor} is today.",
        "reading": "{patient} took a blood pressure today.",
        "visit": "{patient}'s visit to {doctor} is on {day}.",
        "visit_logistics": "{patient}'s visit to {doctor} is on {day}.",
        "memo": "{patient} saw {doctor} on {day}.",
        "reorder": "There are about {days} days of {medicine} left.",
        "reorder_one": "There is about 1 day of {medicine} left.",
        "story_reading": "This is from {patient}'s own blood pressure book.",
        "story_paper": "This is one of {patient}'s own papers.",
        "story_note": "These are {patient}'s own words, from private notes.",
        "story_count": "Nura counted the days {patient} took the tablets.",
        "story_trend": "This is from {patient}'s own blood tests.",
        "story_photo": "{who} chose to share this photo with {patient}.",
        "learning": "This is about {topic}, which is on {patient}'s papers.",
        "needs_doctor_look": "Nura found something about {patient} to ask {doctor} about.",
        "withheld": "Part of {patient}'s papers is not shown here.",
        "recall_action": "{patient}'s {medicine} was named in a safety notice.",
    },
    "ms": {
        "gate": "Semua yang baru hari ini sudah dilihat.",
        "local": "Ini ada di sini kerana ia dekat rumah {patient}.",
        "now_tablets": "{patient} ada ubat dalam senarai.",
        "now_visit": "Lawatan {patient} kepada {doctor} hari ini.",
        "reading": "{patient} ambil tekanan darah hari ini.",
        "visit": "Lawatan {patient} kepada {doctor} pada {day}.",
        "visit_logistics": "Lawatan {patient} kepada {doctor} pada {day}.",
        "memo": "{patient} berjumpa {doctor} pada {day}.",
        "reorder": "{medicine} tinggal lebih kurang {days} hari lagi.",
        "reorder_one": "{medicine} tinggal lebih kurang 1 hari lagi.",
        "story_reading": "Ini dari buku tekanan darah {patient} sendiri.",
        "story_paper": "Ini salah satu surat {patient} sendiri.",
        "story_note": "Ini kata-kata {patient} sendiri, dari nota peribadi.",
        "story_count": "Nura mengira hari {patient} ambil ubat.",
        "story_trend": "Ini dari ujian darah {patient} sendiri.",
        "story_photo": "{who} memilih untuk berkongsi gambar ini dengan {patient}.",
        "learning": "Ini tentang {topic}, yang ada dalam surat-surat {patient}.",
        "needs_doctor_look": "Nura jumpa sesuatu tentang {patient} untuk ditanya kepada {doctor}.",
        "withheld": "Sebahagian surat {patient} tidak ditunjukkan di sini.",
        "recall_action": "{medicine} {patient} disebut dalam satu notis keselamatan.",
    },
    "zh": {
        "gate": "今天新的都看过了。",
        "local": "这个在这里，是因为它在{patient}家附近。",
        "now_tablets": "{patient}的清单上有药。",
        "now_visit": "{patient}今天要看{doctor}。",
        "reading": "{patient}今天量了血压。",
        "visit": "{patient}{day}要看{doctor}。",
        "visit_logistics": "{patient}{day}要看{doctor}。",
        "memo": "{patient}{day}看了{doctor}。",
        "reorder": "{medicine}大概还够{days}天。",
        "reorder_one": "{medicine}大概还够1天。",
        "story_reading": "这来自{patient}自己的血压本。",
        "story_paper": "这是{patient}自己的一份文件。",
        "story_note": "这是{patient}自己的话，来自私人笔记。",
        "story_count": "Nura 数了{patient}吃药的天数。",
        "story_trend": "这来自{patient}自己的验血结果。",
        "story_photo": "{who}选择了和{patient}分享这张照片。",
        "learning": "这是关于{topic}的，它在{patient}的文件里。",
        "needs_doctor_look": "Nura 发现了关于{patient}、需要问{doctor}的事。",
        "withheld": "{patient}的文件有一部分不会显示在这里。",
        "recall_action": "一个安全通知提到了{patient}的{medicine}。",
    },
}
"""Why a card is there, said about him by name."""

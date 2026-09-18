"""The timeline's own words (E03): the three anchors of the spine, what changed since you
last looked, and the lines an answer from Ask is made of.

Every line is tagged `@patient` and written to docs/plain-words.md in English, Malay and
Chinese, with the day and the date said in full (`app.medicines.strings.say_date`, so it is
the same words every time). The services fill the slots — a doctor's name as the directory
holds it, a day, his word for a thing, a number from a fact — and every filled line goes
through `app.safety.plain_words.verify` before it leaves (`verified`). Nothing here judges:
a line says that something was written down, or what a number was, never what it means.

The boundary is not here: recall is an inferring surface, and its line is
`app.safety.boundary`'s for `Surface.RECALL`, the same closing words as on every inferring
surface. The honest line ends on the same "Ask {doctor}." those closing words do.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from app.db import as_utc
from app.medicines.strings import say_date
from app.regions import REGION_TZ, Region
from app.safety.plain_words import verify

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

Lines = Sequence[str]


def language_of(asked: str | None) -> str:
    """One of our languages, or English when the words for it are not on file yet."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


# @patient phrase
WHAT: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood_pressure": "blood pressure",
        "blood_sugar": "sugar test",
        "hba1c": "sugar test",
        "weight": "weight",
        "heart_rate": "pulse",
        "oxygen": "oxygen",
        "temperature": "temperature",
        "lipid_panel": "cholesterol test",
        "kidney_panel": "kidney test",
        "renal_panel": "kidney test",
        "blood_test": "blood test",
        "creatinine": "kidney number",
        "egfr": "kidney filter",
        "potassium": "body salt",
        "medication": "medicine",
        "medicine": "medicine",
        "other": "paper",
    },
    "ms": {
        "blood_pressure": "tekanan darah",
        "blood_sugar": "ujian gula",
        "hba1c": "ujian gula",
        "weight": "berat badan",
        "heart_rate": "nadi",
        "oxygen": "oksigen",
        "temperature": "suhu badan",
        "lipid_panel": "ujian kolesterol",
        "kidney_panel": "ujian buah pinggang",
        "renal_panel": "ujian buah pinggang",
        "blood_test": "ujian darah",
        "creatinine": "nombor buah pinggang",
        "egfr": "tapisan buah pinggang",
        "potassium": "garam badan",
        "medication": "ubat",
        "medicine": "ubat",
        "other": "surat",
    },
    "zh": {
        "blood_pressure": "血压",
        "blood_sugar": "血糖检查",
        "hba1c": "血糖检查",
        "weight": "体重",
        "heart_rate": "脉搏",
        "oxygen": "氧气",
        "temperature": "体温",
        "lipid_panel": "胆固醇检查",
        "kidney_panel": "肾检查",
        "renal_panel": "肾检查",
        "blood_test": "验血",
        "creatinine": "肾指数",
        "egfr": "肾过滤",
        "potassium": "身体的盐",
        "medication": "药",
        "medicine": "药",
        "other": "文件",
    },
}
"""His word for the thing a fact is about, by its subject; "paper" for a subject nobody has
a word for yet, so a change is never silently dropped."""

# @patient phrase
PAPER: Mapping[str, Mapping[str, str]] = {
    "en": {
        "lab_report": "blood test",
        "medicine_label": "medicine label",
        "discharge_letter": "hospital letter",
        "clinic_slip": "letter from the doctor",
        "unknown": "paper",
    },
    "ms": {
        "lab_report": "ujian darah",
        "medicine_label": "label ubat",
        "discharge_letter": "surat hospital",
        "clinic_slip": "surat doktor",
        "unknown": "surat",
    },
    "zh": {
        "lab_report": "验血报告",
        "medicine_label": "药盒标签",
        "discharge_letter": "出院信",
        "clinic_slip": "医生的信",
        "unknown": "文件",
    },
}
"""His word for a paper by the kind the reader took it for, when no fact on it says more."""

# @patient
ANCHORS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "last_checkup": "Your last check-up was with {doctor} on {date}.",
        "last_visit": "Your last visit was to {doctor} on {date}.",
        "next_visit": "Your next visit is to {doctor} on {date}.",
        "no_checkup": "No check-up is written down yet.",
        "no_visit": "No visit is written down yet.",
        "no_next": "No next visit is booked yet.",
    },
    "ms": {
        "last_checkup": "Pemeriksaan terakhir anda dengan {doctor} pada {date}.",
        "last_visit": "Lawatan terakhir anda ke {doctor} pada {date}.",
        "next_visit": "Lawatan anda yang seterusnya ke {doctor} pada {date}.",
        "no_checkup": "Belum ada pemeriksaan yang ditulis.",
        "no_visit": "Belum ada lawatan yang ditulis.",
        "no_next": "Belum ada lawatan seterusnya yang ditempah.",
    },
    "zh": {
        "last_checkup": "{date}是您上一次检查，看{doctor}。",
        "last_visit": "{date}是您上一次看医生，看{doctor}。",
        "next_visit": "{date}是您下一次看医生，看{doctor}。",
        "no_checkup": "还没有写下检查。",
        "no_visit": "还没有写下看医生。",
        "no_next": "还没有预约下一次。",
    },
}
"""The three anchors of the spine, each a whole line, and the line for when there is none."""

# @patient
CHANGED: Mapping[str, Mapping[str, str]] = {
    "en": {
        "first_look": "This is your first look at what changed.",
        "nothing": "Nothing changed since {date}.",
        "new_fact": "A new {what} was written down on {date}.",
        "superseded": "The {what} from {date} was corrected.",
        "new_photo": "A new photo came in on {date}.",
        "new_paper": "A new paper came in on {date}.",
        "visit_booked": "A visit to {doctor} is booked for {date}.",
        "visit_confirmed": "The visit to {doctor} on {date} is confirmed.",
        "visit_attended": "The visit to {doctor} on {date} happened.",
        "visit_not_attended": "The visit to {doctor} on {date} did not happen.",
        "visit_cancelled": "The visit to {doctor} on {date} was cancelled.",
        "medicine_added": "{name} was added on {date}.",
        "medicine_changed": "The new pack of {name} says a different amount.",
        "medicine_ask": "Ask {doctor} about the new amount.",
        "interaction": "There is a new question for {doctor} about your medicines.",
        "red_flag": "On {date} you told Nura something we do not wait for.",
        "key_cut": "{who} was given a key on {date}.",
        "key_closed": "The key {who} held was closed on {date}.",
        "consent_given": "A new agreement was written down on {date}.",
        "consent_withdrawn": "An agreement was withdrawn on {date}.",
        "note_added": "{who} wrote a note about {doctor} on {date}.",
        "episode_opened": "Something new going on was written down on {date}.",
        "attached": "A paper was put with your visit or your illness.",
        "note_left": "{who} left a note on {date}.",
        "family_message": "{who} wrote to the family on {date}.",
        "family_photo": "{who} shared a photo with the family on {date}.",
    },
    "ms": {
        "first_look": "Ini kali pertama anda melihat apa yang berubah.",
        "nothing": "Tiada yang berubah sejak {date}.",
        "new_fact": "{what} yang baru ditulis pada {date}.",
        "superseded": "{what} dari {date} telah dibetulkan.",
        "new_photo": "Gambar baru masuk pada {date}.",
        "new_paper": "Surat baru masuk pada {date}.",
        "visit_booked": "Lawatan ke {doctor} ditempah untuk {date}.",
        "visit_confirmed": "Lawatan ke {doctor} pada {date} sudah pasti.",
        "visit_attended": "Lawatan ke {doctor} pada {date} sudah berlaku.",
        "visit_not_attended": "Lawatan ke {doctor} pada {date} tidak berlaku.",
        "visit_cancelled": "Lawatan ke {doctor} pada {date} dibatalkan.",
        "medicine_added": "{name} ditambah pada {date}.",
        "medicine_changed": "Pek baru {name} menyatakan jumlah yang berbeza.",
        "medicine_ask": "Tanya {doctor} tentang jumlah baru itu.",
        "interaction": "Ada soalan baru untuk {doctor} tentang ubat anda.",
        "red_flag": "Pada {date} anda beritahu Nura sesuatu yang kita tidak tunggu.",
        "key_cut": "{who} diberi kunci pada {date}.",
        "key_closed": "Kunci yang {who} pegang ditutup pada {date}.",
        "consent_given": "Persetujuan baru ditulis pada {date}.",
        "consent_withdrawn": "Satu persetujuan ditarik balik pada {date}.",
        "note_added": "{who} menulis nota tentang {doctor} pada {date}.",
        "episode_opened": "Sesuatu yang baru berlaku ditulis pada {date}.",
        "attached": "Satu surat diletakkan bersama lawatan atau sakit anda.",
        "note_left": "{who} meninggalkan nota pada {date}.",
        "family_message": "{who} menulis kepada keluarga pada {date}.",
        "family_photo": "{who} berkongsi gambar dengan keluarga pada {date}.",
    },
    "zh": {
        "first_look": "这是您第一次看有什么变了。",
        "nothing": "从{date}到现在没有变化。",
        "new_fact": "{date}写下了新的{what}。",
        "superseded": "{date}的{what}改正了。",
        "new_photo": "{date}收到一张新照片。",
        "new_paper": "{date}收到一份新文件。",
        "visit_booked": "预约了{date}看{doctor}。",
        "visit_confirmed": "{date}看{doctor}的预约确定了。",
        "visit_attended": "{date}看{doctor}已经去了。",
        "visit_not_attended": "{date}看{doctor}没有去。",
        "visit_cancelled": "{date}看{doctor}取消了。",
        "medicine_added": "{date}加了{name}。",
        "medicine_changed": "{name}的新药盒写的分量不一样。",
        "medicine_ask": "问{doctor}新的分量。",
        "interaction": "有一个关于您的药的新问题要问{doctor}。",
        "red_flag": "{date}您告诉Nura一件我们不等的事。",
        "key_cut": "{date}给了{who}一把钥匙。",
        "key_closed": "{date}关掉了{who}的钥匙。",
        "consent_given": "{date}写下了一个新的同意。",
        "consent_withdrawn": "{date}撤回了一个同意。",
        "note_added": "{date}{who}写了一条关于{doctor}的留言。",
        "episode_opened": "{date}写下了一件新的事。",
        "attached": "一份文件放到了您看医生或生病的记录里。",
        "note_left": "{who}在{date}留了一条笔记。",
        "family_message": "{who}在{date}给家人留了言。",
        "family_photo": "{who}在{date}给家人分享了一张照片。",
    },
}
"""What changed since the reader last looked, one whole line per change. A new amount on a
pack is told as a question for the doctor, never as the amount (E04). A note someone left on
one of his moments, and what the family wrote or shared in the thread, are told by who and
when, never by what was said (E02-06, E12-02)."""

# @patient
WAITING: Mapping[str, Mapping[str, str]] = {
    "en": {
        "one_card": "One card is waiting for a yes.",
        "cards": "{count} cards are waiting for a yes.",
        "one_not_taken": "One tablet today is not taken yet.",
        "not_taken": "{count} tablets today are not taken yet.",
    },
    "ms": {
        "one_card": "Satu kad menunggu jawapan ya.",
        "cards": "{count} kad menunggu jawapan ya.",
        "one_not_taken": "Satu ubat hari ini belum diambil.",
        "not_taken": "{count} ubat hari ini belum diambil.",
    },
    "zh": {
        "one_card": "有一张卡在等您说好。",
        "cards": "有{count}张卡在等您说好。",
        "one_not_taken": "今天有一次药还没吃。",
        "not_taken": "今天有{count}次药还没吃。",
    },
}
"""What is still waiting, said every time it is looked at: not a change, a to-do."""

# @patient
RECALL: Mapping[str, Mapping[str, str]] = {
    "en": {
        "visit_past": "You saw {doctor} on {date}.",
        "visit_next": "Your next visit is to {doctor} on {date}.",
        "medicine_from": "{doctor} gave you {name}.",
        "medicine_listed": "{name} is on your list of medicines.",
        "paper": "Your {what} from {date} is in your papers.",
        "consult_said": "{doctor} talked about this on {date}.",
        "consult_waiting": "What {doctor} said on {date} is waiting for your yes.",
        "note_yours": "You left a note on {date}.",
        "note_theirs": "{who} left a note on {date}.",
        "transcript_said": "This was said when you saw {doctor} on {date}.",
    },
    "ms": {
        "visit_past": "Anda berjumpa {doctor} pada {date}.",
        "visit_next": "Lawatan anda yang seterusnya ke {doctor} pada {date}.",
        "medicine_from": "{doctor} memberi anda {name}.",
        "medicine_listed": "{name} ada dalam senarai ubat anda.",
        "paper": "{what} anda dari {date} ada dalam surat-surat anda.",
        "consult_said": "{doctor} bercakap tentang perkara ini pada {date}.",
        "consult_waiting": "Apa yang {doctor} kata pada {date} menunggu jawapan ya daripada anda.",
        "note_yours": "Anda meninggalkan nota pada {date}.",
        "note_theirs": "{who} meninggalkan nota pada {date}.",
        "transcript_said": "Ini dikatakan semasa anda berjumpa {doctor} pada {date}.",
    },
    "zh": {
        "visit_past": "您{date}看了{doctor}。",
        "visit_next": "{date}是您下一次看医生，看{doctor}。",
        "medicine_from": "{doctor}给了您{name}。",
        "medicine_listed": "{name}在您的药单上。",
        "paper": "您{date}的{what}在您的文件里。",
        "consult_said": "{doctor}在{date}讲过这件事。",
        "consult_waiting": "{doctor}在{date}说的话，在等您说好。",
        "note_yours": "您在{date}留了一条笔记。",
        "note_theirs": "{who}在{date}留了一条笔记。",
        "transcript_said": "这是您{date}看{doctor}时说的。",
    },
}
"""The lines an answer is made of. Each says what is written down and when, filled only with
the values of the facts it cites; none says what a number means. `consult_said` is a line of
a recorded visit (E03-05): it cites the summary item and the stretch of the recording where
the doctor said it, which the phone plays on a tap — once he has confirmed the card. Until then
`consult_waiting` says the card is waiting for his yes, and cites the card only. `note_yours`
and `note_theirs` are a note on one of his moments (E02-06), cited with the note and its event;
the words heard in it are the note's own and played from it. `transcript_said` heads a
sentence found in a confirmed visit's transcript (E02-05), which is the room's words, quoted."""

# @patient
ASK_STEPS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "visits": "Checking your visits.",
        "readings": "Looking at your blood pressure book.",
        "medicines": "Checking your medicines.",
        "records": "Looking at your papers.",
        "feelings": "Checking your feelings notes.",
        "search_online": "Looking online.",
    },
    "ms": {
        "visits": "Menyemak lawatan anda.",
        "readings": "Melihat buku tekanan darah anda.",
        "medicines": "Menyemak ubat anda.",
        "records": "Melihat surat anda.",
        "feelings": "Menyemak nota perasaan anda.",
        "search_online": "Melihat di web.",
    },
    "zh": {
        "visits": "正在查看您看医生的记录。",
        "readings": "正在查看您的血压本。",
        "medicines": "正在查看您的药。",
        "records": "正在查看您的文件。",
        "feelings": "正在查看您的感受记录。",
        "search_online": "正在网上查看。",
    },
}
"""What Ask's trace says while it works (spec 'Conversation, waiting and thinking'), one line
per part of the record `app.search.ask.recall_stream` actually just read — never a step that
was not real, never held back to look slower. Keyed by `app.search.ask.STEP_KEYS`, the order
the parts are read in, plus the two the agent asker alone can take (`app.llm.ask_agent.
ClaudeAsker`): `feelings`, his notes off the feeling cloud, and `search_online`, the allowlisted
web (`app.delivery.feed.claude_adapters.ClaudeSearcher`) — never a row itself, either way. A
caregiver hears the `_THEIRS` twin below (`app.channels.about_him`), by name, never in his
voice."""

# @patient phrase
ASK_STEP_NAMES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "visits": "visits",
        "readings": "blood pressure book",
        "medicines": "medicines",
        "records": "papers",
        "feelings": "feelings notes",
        "search_online": "online",
    },
    "ms": {
        "visits": "lawatan",
        "readings": "buku tekanan darah",
        "medicines": "ubat",
        "records": "surat",
        "feelings": "nota perasaan",
        "search_online": "dalam talian",
    },
    "zh": {
        "visits": "看医生的记录",
        "readings": "血压本",
        "medicines": "药",
        "records": "文件",
        "feelings": "感受记录",
        "search_online": "网上",
    },
}
"""The short name for each part `ASK_STEPS` reads — a bare noun, not "your" or "his" and not a
sentence, for the trace's collapsed line, "What Nura looked at: {parts}" — the same words
whoever is asking, so it needs no `_THEIRS` twin."""

# @patient
IMPORT_STEPS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "stored": "Nura is keeping your paper safe.",
        "reading": "Nura is looking at your paper.",
        "found": "Nura found {kind} in your paper.",
        "found_at": "Nura found {kind} in your paper, from {facility}.",
        "red_flag_checked": "Nura checked your paper closely.",
        "linked_medicine": "This is about {medicine}, already on your list.",
        "linked_visit": "This matches a visit already on your list.",
        "ready": "Your paper is ready for you to check.",
    },
    "ms": {
        "stored": "Nura sedang simpan surat anda dengan selamat.",
        "reading": "Nura sedang melihat surat anda.",
        "found": "Nura jumpa {kind} dalam surat anda.",
        "found_at": "Nura jumpa {kind} dalam surat anda, dari {facility}.",
        "red_flag_checked": "Nura sudah semak surat anda jika ada apa-apa yang segera.",
        "linked_medicine": "Ini tentang {medicine}, sudah ada dalam senarai anda.",
        "linked_visit": "Ini sepadan dengan lawatan yang sudah ada dalam senarai anda.",
        "ready": "Surat anda sedia untuk anda semak.",
    },
    "zh": {
        "stored": "Nura正在安全地保存您的文件。",
        "reading": "Nura正在看您的文件。",
        "found": "Nura在您的文件里找到了{kind}。",
        "found_at": "Nura在您的文件里找到了{kind}，来自{facility}。",
        "red_flag_checked": "Nura检查了您的文件，看看有没有紧急的事。",
        "linked_medicine": "这和您已经在吃的{medicine}有关。",
        "linked_visit": "这和您名单上已有的一次看医生记录相符。",
        "ready": "您的文件已准备好让您检查。",
    },
}
"""What the Add flow's trace says while it works (docs/design-direction.md 'Conversation,
waiting and thinking'), one line per real stage `app.ingestion.review.review_artifact_stream`
actually just finished — never a step that was not real (its own module docstring). Keyed by
`app.ingestion.review.ImportStepKey`. `found`/`found_at` and `linked_medicine`/`linked_visit`
are two lines each because a template's slots are always filled (docs/plain-words.md's own
verifier fills every `{slot}` it finds): a page with no facility line on it, or with no real
match, uses the shorter template rather than a slot filled with nothing."""

# @patient phrase
DOCUMENT_KIND_WORD: Mapping[str, Mapping[str, str]] = {
    "en": {
        "lab_report": "a blood test",
        "medicine_label": "a medicine label",
        "discharge_letter": "a hospital letter",
        "clinic_slip": "a clinic slip",
        "handwritten_prescription": "a prescription",
        "insurance_letter": "an insurance letter",
        "insurance_policy": "an insurance letter",
        "insurance_claim": "an insurance claim",
        "device_screen": "a machine screen",
        "other": "a paper",
        "not_health": "a paper",
        "unknown": "a paper",
        "unsupported_file_type": "a paper",
    },
    "ms": {
        "lab_report": "ujian darah",
        "medicine_label": "label ubat",
        "discharge_letter": "surat hospital",
        "clinic_slip": "slip klinik",
        "handwritten_prescription": "preskripsi",
        "insurance_letter": "surat insurans",
        "insurance_policy": "surat insurans",
        "insurance_claim": "tuntutan insurans",
        "device_screen": "bacaan",
        "other": "surat",
        "not_health": "surat",
        "unknown": "surat",
        "unsupported_file_type": "surat",
    },
    "zh": {
        "lab_report": "验血",
        "medicine_label": "药盒标签",
        "discharge_letter": "出院信",
        "clinic_slip": "诊所单据",
        "handwritten_prescription": "处方",
        "insurance_letter": "保险信",
        "insurance_policy": "保险信",
        "insurance_claim": "保险索赔",
        "device_screen": "读数",
        "other": "文件",
        "not_health": "文件",
        "unknown": "文件",
        "unsupported_file_type": "文件",
    },
}
"""The bare noun `IMPORT_STEPS`' `{kind}` slot takes — his words for the kind of paper
(`app.ingestion.extract.DocumentKind`), never "your" or a sentence, the same reason
`ASK_STEP_NAMES` needs no `_THEIRS` twin: the sentence around it already carries who it is
for."""

# @patient
NFW_STEPS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "checking": "Nura is checking on you.",
        "tablets": "Nura checked your tablets today.",
        "medicines": "Nura checked your recent medicines.",
        "family": "Nura told your family.",
        "ready": "Your card is ready.",
    },
    "ms": {
        "checking": "Nura sedang menyemak keadaan anda.",
        "tablets": "Nura sudah semak ubat anda hari ini.",
        "medicines": "Nura sudah semak ubat anda yang baru.",
        "family": "Nura sudah beritahu keluarga anda.",
        "ready": "Kad anda sudah sedia.",
    },
    "zh": {
        "checking": "Nura正在为您检查。",
        "tablets": "Nura检查了您今天的药。",
        "medicines": "Nura检查了您最近的药。",
        "family": "Nura已经告诉您的家人。",
        "ready": "您的卡片已经准备好。",
    },
}
"""What the not-feeling-well trace says while it works, one line per real read
`app.safety.not_feeling_well.not_feeling_well_stream` does before the card — streamed only
after the red-flag path has already run its course (module docstring: "the trace must never
delay it"), so `checking` is the first byte on the wire, never the first thing that happens."""

# @patient
READING: Mapping[str, Lines] = {
    "en": ("Your blood pressure on {date} was {top_number} over {bottom_number}.",),
    "ms": ("Tekanan darah anda pada {date} ialah {top_number} atas {bottom_number}.",),
    "zh": ("{date}您量了血压。", "您的血压是{top_number}比{bottom_number}。"),
}
"""A blood pressure said back: the day, and the two numbers he wrote down. In Chinese the day
itself carries two numbers, so the numbers are a second line (rule 10)."""

# @patient
HONEST: Mapping[str, Lines] = {
    "en": ("Nura does not have that written down.", "Ask {doctor}."),
    "ms": ("Nura tidak ada catatan tentang itu.", "Tanya {doctor}."),
    "zh": ("Nura没有记下这件事。", "问{doctor}。"),
}
"""When nothing on the record answers the question: said plainly, never guessed."""

# @patient
REROUTE: Mapping[str, Lines] = {
    "en": ("Ask {doctor} before you change any medicine.",),
    "ms": ("Tanya {doctor} sebelum anda ubah apa-apa ubat.",),
    "zh": ("改任何药之前，先问{doctor}。",),
}
"""A question that would change treatment is a question for the doctor (safety.md)."""

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}
"""When no doctor's name is written down."""

# @patient phrase
SOMEONE: Mapping[str, str] = {"en": "Someone", "ms": "Seseorang", "zh": "有人"}
"""When the person has not given a name yet."""

_SLOTS = ("doctor", "who", "what", "name", "date", "count", "top_number", "bottom_number")


def _fill(template: str, language: str, slots: Mapping[str, str]) -> str:
    """The template with every slot filled, and the first letter a capital where the
    language has capitals (a line may open with his name for a medicine)."""
    values = {slot: "" for slot in _SLOTS}
    values["doctor"] = YOUR_DOCTOR[language]
    values["who"] = SOMEONE[language]
    values.update({key: value for key, value in slots.items() if value})
    line = template.format(**values)
    if language != "zh" and line[:1].islower():
        line = line[:1].upper() + line[1:]
    return line


def what_word(subject: str, language: str) -> str:
    """His word for the thing a fact is about, or "paper" when nobody has one yet."""
    found = WHAT[language]
    return found.get(subject, found["other"])


def paper_word(document_kind: str | None, language: str) -> str:
    """His word for a paper by its kind."""
    found = PAPER[language]
    return found.get(document_kind or "unknown", found["unknown"])


def day_of(moment: datetime, region: Region) -> date:
    """The day a moment fell on, on the patient's own clock."""
    return as_utc(moment).astimezone(REGION_TZ[region]).date()


def said_date(moment: datetime, region: Region, language: str) -> str:
    """'Monday 14 September', on his clock, in his language."""
    return say_date(day_of(moment, region), language)


def anchor_line(key: str, language: str, *, doctor: str | None = None, when: str = "") -> str:
    return _fill(ANCHORS[language][key], language, {"doctor": doctor or "", "date": when})


def changed_line(key: str, language: str, **slots: str) -> str:
    return _fill(CHANGED[language][key], language, slots)


def waiting_line(key: str, language: str, **slots: str) -> str:
    return _fill(WAITING[language][key], language, slots)


def recall_line(key: str, language: str, **slots: str) -> str:
    return _fill(RECALL[language][key], language, slots)


def reading_lines(language: str, *, date: str, top_number: str, bottom_number: str) -> list[str]:
    slots = {"date": date, "top_number": top_number, "bottom_number": bottom_number}
    return [_fill(line, language, slots) for line in READING[language]]


def honest_lines(language: str, doctor: str | None) -> list[str]:
    return [_fill(line, language, {"doctor": doctor or ""}) for line in HONEST[language]]


def reroute_lines(language: str, doctor: str | None) -> list[str]:
    return [_fill(line, language, {"doctor": doctor or ""}) for line in REROUTE[language]]


def verified(line: str, language: str) -> bool:
    """Whether a filled line passes docs/plain-words.md. A note (an eleven-word line) is not
    a failure; any failure keeps the line from leaving."""
    return not any(finding.severity == "fail" for finding in verify(line, language, "line"))


def catalogue() -> list[str]:
    """Every whole-line template here, in every language, for the tests."""
    found: list[str] = []
    for table in (ANCHORS, CHANGED, WAITING, RECALL):
        for by_key in table.values():
            found.extend(by_key.values())
    for lines in (READING, HONEST, REROUTE):
        for each in lines.values():
            found.extend(each)
    return found


__all__ = [
    "ANCHORS",
    "ASK_STEPS",
    "ASK_STEP_NAMES",
    "CHANGED",
    "DOCUMENT_KIND_WORD",
    "HONEST",
    "IMPORT_STEPS",
    "IMPORT_STEPS_THEIRS",
    "LANGUAGES",
    "NFW_STEPS",
    "NFW_STEPS_THEIRS",
    "READING",
    "RECALL",
    "REROUTE",
    "WAITING",
    "WHAT",
    "YOUR_DOCTOR",
    "anchor_line",
    "catalogue",
    "changed_line",
    "day_of",
    "honest_lines",
    "language_of",
    "paper_word",
    "reading_lines",
    "recall_line",
    "reroute_lines",
    "said_date",
    "verified",
    "waiting_line",
    "what_word",
]

# --- about him, to someone else (D1) ------------------------------------------------------------
# The same cards, said about him by name to a family member reading his papers with her own key:
# each twin mirrors its original's keys and places, "{patient}" his name as the family writes it.
# Chosen on the backend for a key that is not his (`app.channels.about_him`); a line with no twin
# that speaks to him is not shown to anyone else.

# @patient
CHANGED_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "first_look": "This is the first look at what changed.",
        "interaction": "There is a new question for {doctor} about {patient}'s medicines.",
        "red_flag": "On {date} {patient} told Nura something we do not wait for.",
        "attached": "A paper was put with {patient}'s visit or illness.",
    },
    "ms": {
        "first_look": "Ini kali pertama melihat apa yang berubah.",
        "interaction": "Ada soalan baru untuk {doctor} tentang ubat {patient}.",
        "red_flag": "Pada {date} {patient} beritahu Nura sesuatu yang kita tidak tunggu.",
        "attached": "Satu surat diletakkan bersama lawatan atau sakit {patient}.",
    },
    "zh": {
        "first_look": "这是第一次看有什么变了。",
        "interaction": "有一个关于{patient}的药的新问题要问{doctor}。",
        "red_flag": "{date}{patient}告诉Nura一件我们不等的事。",
        "attached": "一份文件放到了{patient}看医生或生病的记录里。",
    },
}
"""What changed, said about him by name; the first look is the reader's own, said with no "your"."""

# @patient
ANCHORS_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "last_checkup": "{patient}'s last check-up was with {doctor} on {date}.",
        "last_visit": "{patient}'s last visit was to {doctor} on {date}.",
        "next_visit": "{patient}'s next visit is to {doctor} on {date}.",
    },
    "ms": {
        "last_checkup": "Pemeriksaan terakhir {patient} dengan {doctor} pada {date}.",
        "last_visit": "Lawatan terakhir {patient} ke {doctor} pada {date}.",
        "next_visit": "Lawatan {patient} yang seterusnya ke {doctor} pada {date}.",
    },
    "zh": {
        "last_checkup": "{date}是{patient}上一次检查，看{doctor}。",
        "last_visit": "{date}是{patient}上一次看医生，看{doctor}。",
        "next_visit": "{date}是{patient}下一次看医生，看{doctor}。",
    },
}
"""The timeline's three anchors said about him by name, for a key that is not his."""

# @patient
ASK_STEPS_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "visits": "Checking {patient}'s visits.",
        "readings": "Looking at {patient}'s blood pressure book.",
        "medicines": "Checking {patient}'s medicines.",
        "records": "Looking at {patient}'s papers.",
        "feelings": "Checking {patient}'s feelings notes.",
        "search_online": "Looking online for {patient}.",
    },
    "ms": {
        "visits": "Menyemak lawatan {patient}.",
        "readings": "Melihat buku tekanan darah {patient}.",
        "medicines": "Menyemak ubat {patient}.",
        "records": "Melihat surat {patient}.",
        "feelings": "Menyemak nota perasaan {patient}.",
        "search_online": "Melihat di internet untuk {patient}.",
    },
    "zh": {
        "visits": "正在查看{patient}看医生的记录。",
        "readings": "正在查看{patient}的血压本。",
        "medicines": "正在查看{patient}的药。",
        "records": "正在查看{patient}的文件。",
        "feelings": "正在查看{patient}的感受记录。",
        "search_online": "正在为{patient}在网上查看。",
    },
}
"""`ASK_STEPS`, said about him by name, for a key that is not his."""

# @patient
IMPORT_STEPS_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "stored": "Nura is keeping {patient}'s paper safe.",
        "reading": "Nura is looking at {patient}'s paper.",
        "found": "Nura found {kind} for {patient}.",
        "found_at": "Nura found {kind} for {patient}, from {facility}.",
        "red_flag_checked": "Nura checked {patient}'s paper closely.",
        "linked_medicine": "This is about {medicine}, already on {patient}'s list.",
        "linked_visit": "This matches a visit already on {patient}'s list.",
        "ready": "{patient}'s paper is ready to check.",
    },
    "ms": {
        "stored": "Nura sedang simpan surat {patient} dengan selamat.",
        "reading": "Nura sedang melihat surat {patient}.",
        "found": "Nura jumpa {kind} untuk {patient}.",
        "found_at": "Nura jumpa {kind} untuk {patient}, dari {facility}.",
        "red_flag_checked": "Nura sudah semak jika ada apa-apa yang segera untuk {patient}.",
        "linked_medicine": "Ini tentang {medicine}, sudah ada dalam senarai {patient}.",
        "linked_visit": "Ini sepadan dengan lawatan yang sudah ada dalam senarai {patient}.",
        "ready": "Surat {patient} sedia untuk disemak.",
    },
    "zh": {
        "stored": "Nura正在安全地保存{patient}的文件。",
        "reading": "Nura正在看{patient}的文件。",
        "found": "Nura为{patient}找到了{kind}。",
        "found_at": "Nura为{patient}找到了{kind}，来自{facility}。",
        "red_flag_checked": "Nura为{patient}检查了是否有紧急的事。",
        "linked_medicine": "这和{patient}已经在吃的{medicine}有关。",
        "linked_visit": "这和{patient}名单上已有的一次看医生记录相符。",
        "ready": "{patient}的文件已准备好检查。",
    },
}
"""`IMPORT_STEPS`, said about him by name, for a key that is not his."""

# @patient
NFW_STEPS_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "checking": "Nura is checking on {patient}.",
        "tablets": "Nura checked {patient}'s tablets today.",
        "medicines": "Nura checked {patient}'s recent medicines.",
        "family": "Nura told {patient}'s family.",
        "ready": "{patient}'s card is ready.",
    },
    "ms": {
        "checking": "Nura sedang menyemak keadaan {patient}.",
        "tablets": "Nura sudah semak ubat {patient} hari ini.",
        "medicines": "Nura sudah semak ubat {patient} yang baru.",
        "family": "Nura sudah beritahu keluarga {patient}.",
        "ready": "Kad {patient} sudah sedia.",
    },
    "zh": {
        "checking": "Nura正在为{patient}检查。",
        "tablets": "Nura检查了{patient}今天的药。",
        "medicines": "Nura检查了{patient}最近的药。",
        "family": "Nura已经告诉{patient}的家人。",
        "ready": "{patient}的卡片已经准备好。",
    },
}
"""`NFW_STEPS`, said about him by name, for a key that is not his."""

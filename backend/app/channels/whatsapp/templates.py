"""The six approved templates: the only proactive messages the number may send (E19-01).

Outside the 24-hour customer-service window a business may send nothing but a template Meta
has approved, with its slots filled. So everything proactive — the morning card, the visit
card, the reorder, the family digest, the feeling check-in, the red-flag notice (E19), and the
ladder's two asks, the reorder to the family, the count, the papers waiting and a family
message (E11), and the notice of a voice note Nura could not hear (#158) — is one of these
eighteen, submitted once and named here: its slots, and the words a patient reads in each
language Nura speaks, written to `docs/plain-words.md` and checked by `make plain-words`.
`render` fills a template; the send path verifies the filled text again at run time.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.errors import Refusal

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"


class NotATemplate(Refusal):
    """No approved template by that name."""


class MissingSlot(Refusal):
    """A template's slots are filled exactly: none missing, none extra."""


@dataclass(frozen=True, slots=True)
class Template:
    name: str
    slots: tuple[str, ...]
    text: Mapping[str, str]
    """The body per language; every `{slot}` in it is one of `slots`."""
    approved: bool = True
    """Whether Meta has approved it. A pending template is sent on a dev run only; anywhere
    else `send` refuses it (`TemplateNotApproved`) and the delivery tries its next channel."""


# @patient
MORNING_CARD = Template(
    "morning_card",
    ("name", "day", "doses"),
    {
        "en": (
            "Good morning, {name}, this is Nura.\n"
            "Today is {day}.\n"
            "{doses}\n"
            "When you can, take your blood pressure.\n"
            "Send me the 2 numbers."
        ),
        "ms": (
            "Selamat pagi, {name}, ini Nura.\n"
            "Hari ini {day}.\n"
            "{doses}\n"
            "Bila ada masa, ambil tekanan darah anda.\n"
            "Hantar 2 nombor itu kepada saya."
        ),
        "zh": "早上好，{name}，我是 Nura。\n今天是 {day}。\n{doses}\n有空的时候，量一下血压。\n把 2 个数字发给我。",
    },
)
"""The patient's Level 0 morning: today's doses, one thing to measure."""

# @patient
VISIT_REMINDER = Template(
    "visit_reminder",
    ("name", "doctor", "day", "time", "who"),
    {
        "en": "{name}, you see {doctor} on {day} at {time}.\n{who} will take you.",
        "ms": "{name}, anda berjumpa {doctor} pada {day} jam {time}.\n{who} akan bawa anda.",
        "zh": "{name}，{day} {time}，您看{doctor}。\n{who}会带您去。",
    },
)

# @patient
REORDER = Template(
    "reorder",
    ("name", "medicine", "day", "who"),
    {
        "en": "{name}, {medicine} runs out on {day}.\n{who} will order more.",
        "ms": "{name}, {medicine} akan habis pada {day}.\n{who} akan pesan lagi.",
        "zh": "{name}，{medicine} {day} 就吃完了。\n{who}会再订。",
    },
)

# @patient
FAMILY_DIGEST = Template(
    "family_digest",
    ("name", "count"),
    {
        "en": "Nura wrote down {count} things about {name} this week.\nYou can read them in the app.",
        "ms": "Nura menulis {count} perkara tentang {name} minggu ini.\nAnda boleh baca dalam aplikasi.",
        "zh": "这个星期，Nura 为{name}记下了 {count} 件事。\n您可以在应用里看。",
    },
)

# @patient
FEELING_CHECK_IN = Template(
    "feeling_check_in",
    ("name",),
    {
        "en": "Hello {name}, this is Nura.\nHow are you feeling today?\nAnswer OK, tired or pain.",
        "ms": "Helo {name}, ini Nura.\nApa khabar hari ini?\nJawab OK, letih atau sakit.",
        "zh": "{name}您好，我是 Nura。\n今天感觉怎么样？\n回答：好、累，或者痛。",
    },
)
"""Three words, one tap each; the answer is his own word about himself."""

# @patient
RED_FLAG_NOTICE = Template(
    "red_flag_notice",
    ("name", "who", "doctor"),
    {
        "en": "This one we do not wait for.\n{who} said {name} is not well.\nCall {doctor} today.",
        "ms": "Yang ini kita tidak tunggu.\n{who} kata {name} tidak sihat.\nTelefon {doctor} hari ini.",
        "zh": "这个不能等。\n{who}说{name}不舒服。\n今天就打电话给{doctor}。",  # approved words; see below
    },
)

# The Chinese red-flag notice above is the wording Meta approved: "这个不能等。". The card and the
# replies now say "这个我们不等。" (docs/plain-words.md §6, E22-02), and an approved template is
# not edited in place. So the same notice in today's words is submitted again as its own
# template, `RED_FLAG_NOTICE_V2`, below; the ladder sends it wherever the number approves it and
# this one otherwise, so a flag never waits on Meta. `make language` notes the old words until
# this one is retired.

# @patient
RED_FLAG_NOTICE_V2 = Template(
    "red_flag_notice_v2",
    ("name", "who", "doctor"),
    {
        "en": "This one we do not wait for.\n{who} said {name} is not well.\nCall {doctor} today.",
        "ms": "Yang ini kita tidak tunggu.\n{who} kata {name} tidak sihat.\nTelefon {doctor} hari ini.",
        "zh": "这个我们不等。\n{who}说{name}不舒服。\n今天就打电话给{doctor}。",
    },
    approved=False,
)
"""The red-flag notice in the glossary's words (#160): the English and the Malay as approved, the
Chinese as the card says it. Pending Meta's approval, then it replaces `RED_FLAG_NOTICE`."""

# @patient
DOSE_REMINDER = Template(
    "dose_reminder",
    ("name", "medicine", "anchor"),
    {
        "en": "{name}, this is Nura.\nHave you had {medicine} {anchor}?\nWhen you have, reply Taken.",
        "ms": "{name}, ini Nura.\nSudahkah anda ambil {medicine} {anchor}?\nBila sudah, balas Sudah ambil.",
        "zh": "{name}，我是 Nura。\n您{anchor}吃了{medicine}吗？\n吃了的话，请回复“吃了”。",
    },
    approved=False,
)
"""The first rung of the ladder (E11-06): the tablet's window closed with no Taken."""

# @patient
DOSE_CHECK = Template(
    "dose_check",
    ("name", "medicine", "anchor"),
    {
        "en": (
            "{name} has not said Taken for {medicine} {anchor} yet.\n"
            "Please check on {name}.\n"
            "When {name} has had it, reply given."
        ),
        "ms": (
            "{name} belum kata Sudah ambil untuk {medicine} {anchor}.\n"
            "Tolong tengok {name}.\n"
            "Bila {name} sudah ambil, balas sudah beri."
        ),
        "zh": "{name}{anchor}的{medicine}还没有说“吃了”。\n请去看看{name}。\n{name}吃了以后，请回复“给了”。",
    },
    approved=False,
)
"""The rungs after him: the helper, the one on duty, the chief."""

# @patient
REORDER_FAMILY = Template(
    "reorder_family",
    ("name", "medicine", "day"),
    {
        "en": "{name}'s tablets are running low.\n{medicine} runs out on {day}.\nCan you order more for {name}?",
        "ms": "Ubat {name} hampir habis.\n{medicine} habis pada {day}.\nTolong pesan lagi untuk {name}.",
        "zh": "{name}的药快吃完了。\n{medicine}{day}就吃完了。\n请再为{name}订一些。",
    },
    approved=False,
)
"""The reorder date reached, to the one who orders (E04's count)."""

# @patient
DOSES_COUNT = Template(
    "doses_count",
    ("name", "count"),
    {
        "en": (
            "{name} did not say Taken {count} times this week.\n"
            "This is only a count.\n"
            "You can see which ones in the app."
        ),
        "ms": (
            "Minggu ini {name} tidak kata Sudah ambil sebanyak {count} kali.\n"
            "Ini hanya kiraan.\n"
            "Anda boleh lihat yang mana dalam aplikasi."
        ),
        "zh": "这个星期，{name}有 {count} 次没有说“吃了”。\n这只是次数。\n您可以在应用里看是哪几次。",
    },
    approved=False,
)
"""The pattern (three or more in seven days), to the one on duty: a count, never a finding."""

# @patient
PAPERS_WAITING = Template(
    "papers_waiting",
    ("name",),
    {
        "en": "New papers for {name} are waiting for your yes.\nYou can check them in the app.",
        "ms": "Surat baru untuk {name} menunggu jawapan ya anda.\nAnda boleh semak dalam aplikasi.",
        "zh": "{name}有新文件在等您确认。\n您可以在应用里看。",
    },
    approved=False,
)
"""A paper read into a review card, to the chief: that there are papers, never what they say."""

# @patient
FAMILY_NOTE = Template(
    "family_note",
    ("who", "message"),
    {
        "en": "{who} sent you a message.\n{message}",
        "ms": "{who} menghantar mesej kepada anda.\n{message}",
        "zh": "{who}给您发了一条消息。\n{message}",
    },
    approved=False,
)
"""A chief's message to him, come due (E12-06): her previewed lines, exactly."""

# @patient
RED_FLAG_NOTICE_SELF = Template(
    "red_flag_notice_self",
    ("name", "doctor"),
    {
        "en": "This one we do not wait for.\n{name} is not feeling well.\nCall {doctor} today.",
        "ms": "Yang ini kita tidak tunggu.\n{name} rasa tidak sihat.\nTelefon {doctor} hari ini.",
        "zh": "这个我们不等。\n{name}不舒服。\n今天就打电话给{doctor}。",
    },
    approved=False,
)
"""The red-flag notice when he raised it himself: his name, no one else's word about him."""

# @patient
RED_FLAG_NOTICE_AMBIGUOUS = Template(
    "red_flag_notice_ambiguous",
    ("who", "name"),
    {
        "en": (
            "This one we do not wait for.\n"
            "{who} said someone in the family is not well.\n"
            "It may be about {name}.\n"
            "Call {who} now."
        ),
        "ms": (
            "Yang ini kita tidak tunggu.\n"
            "{who} kata seseorang dalam keluarga tidak sihat.\n"
            "Mungkin tentang {name}.\n"
            "Telefon {who} sekarang."
        ),
        "zh": "这个我们不等。\n{who}说家里有人不舒服。\n可能是{name}。\n现在就打电话给{who}。",
    },
    approved=False,
)
"""A red flag from someone on more than one family's list, before they said which: raised on
each, and each family told it may be about theirs."""

# @patient
NUDGE = Template(
    "nudge",
    ("message",),
    {
        "en": "Nura has a note for you.\n{message}",
        "ms": "Nura ada nota untuk anda.\n{message}",
        "zh": "Nura 有一句话要告诉您。\n{message}",
    },
    approved=False,
)
"""The day's smart nudge (E17-03), sent by E11's engine: the planner's lines, exactly."""

# @patient
UNHEARD_NOTE_NOTICE = Template(
    "unheard_note_notice",
    ("name",),
    {
        "en": (
            "{name} sent a voice note to Nura.\n"
            "Nura could not hear this note.\n"
            "Listen to it in the app, or call {name} now."
        ),
        "ms": (
            "{name} hantar nota suara kepada Nura.\n"
            "Nura tidak dapat mendengar nota ini.\n"
            "Dengar nota itu dalam aplikasi, atau telefon {name} sekarang."
        ),
        "zh": "{name}给 Nura 发了一条语音留言。\nNura 听不清这段录音。\n请在应用里听，或者现在就打电话给{name}。",
    },
    approved=False,
)
"""His voice note Nura could not hear, to his chief whose key opens his notes (#158): a red
word in it could not be read, so a person listens. His words stay in his note, not here."""

# @patient
UNHEARD_NOTE_NOTICE_CALL = Template(
    "unheard_note_notice_call",
    ("name",),
    {
        "en": "{name} sent a voice note to Nura.\nNura could not hear this note.\nCall {name} now.",
        "ms": (
            "{name} hantar nota suara kepada Nura.\n"
            "Nura tidak dapat mendengar nota ini.\n"
            "Telefon {name} sekarang."
        ),
        "zh": "{name}给 Nura 发了一条语音留言。\nNura 听不清这段录音。\n现在就打电话给{name}。",
    },
    approved=False,
)
"""The same notice where there is nothing she can open — the note could not be fetched, or her
key does not open his notes — so the one thing to do is to call him."""

TEMPLATES: Mapping[str, Template] = {
    template.name: template
    for template in (
        MORNING_CARD,
        VISIT_REMINDER,
        REORDER,
        FAMILY_DIGEST,
        FEELING_CHECK_IN,
        RED_FLAG_NOTICE,
        DOSE_REMINDER,
        DOSE_CHECK,
        REORDER_FAMILY,
        DOSES_COUNT,
        PAPERS_WAITING,
        FAMILY_NOTE,
        RED_FLAG_NOTICE_SELF,
        RED_FLAG_NOTICE_AMBIGUOUS,
        NUDGE,
        RED_FLAG_NOTICE_V2,
        UNHEARD_NOTE_NOTICE,
        UNHEARD_NOTE_NOTICE_CALL,
    )
}
TEMPLATE_NAMES: tuple[str, ...] = tuple(TEMPLATES)
"""All eighteen, in the order they are submitted: E19's six (approved), then E11's nine, the
red-flag notice in the glossary's words (#160) and #158's two, all pending Meta's approval
(`approved=False`)."""


def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def template_named(name: str) -> Template:
    found = TEMPLATES.get(name)
    if found is None:
        raise NotATemplate(f"no approved template named {name!r}")
    return found


def render(name: str, language: str | None, params: Mapping[str, str]) -> str:
    """The template's body in `language`, every slot filled, or a refusal."""
    template = template_named(name)
    wanted = set(template.slots)
    given = set(params)
    if wanted != given:
        raise MissingSlot(f"{name} takes {sorted(wanted)}, given {sorted(given)}")
    return template.text[language_of(language)].format(**params)

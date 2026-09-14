"""The six approved templates: the only proactive messages the number may send (E19-01).

Outside the 24-hour customer-service window a business may send nothing but a template Meta
has approved, with its slots filled. So everything proactive — the morning card, the visit
card, the reorder, the family digest, the feeling check-in, the red-flag notice — is one of
these six, submitted once and named here: its slots, and the words a patient reads in each
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

# The Chinese red-flag notice above is the wording submitted for approval: "这个不能等。". The card
# and the replies now say "这个我们不等。" (docs/plain-words.md §6, E22-02); `make language` notes
# the difference as a follow-up, and the template changes only when it is submitted again.

TEMPLATES: Mapping[str, Template] = {
    template.name: template
    for template in (
        MORNING_CARD,
        VISIT_REMINDER,
        REORDER,
        FAMILY_DIGEST,
        FEELING_CHECK_IN,
        RED_FLAG_NOTICE,
    )
}
TEMPLATE_NAMES: tuple[str, ...] = tuple(TEMPLATES)
"""The six, in the order they are submitted for approval."""


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

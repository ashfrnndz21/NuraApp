"""The strings catalogue: every sentence a patient reads or hears that the backend writes.

The first patient-facing strings live here, so that `make plain-words` and the reviewer look
in one place. Each is tagged `@patient` and follows `docs/plain-words.md`: whole sentences,
one idea per line, say what to do and who does the next thing, the same words every time.

Every line is here in English, Malay and Chinese (`TEXT`), filed under the same key in each,
so the translation memory (`app.language.memory`, `make language`) can hold the three to one
another. Where the web client already says the same English line, the Malay and Chinese are
its words, not new ones. The English constants below (`CODE_WORKS_FOR`, `COULD_NOT_READ`, …)
are the English lines, kept by name for the callers that do not yet know the language.
"""

from __future__ import annotations

from collections.abc import Mapping

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

Lines = tuple[str, ...]

# @patient
TEXT: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        # The one line every code message and the sign-in screen share.
        "code_works_for": ("The code works for 10 minutes.",),
        # The message a phone receives when the person asked for the code himself.
        "phone_code_self": (
            "Your Nura code is {code}.",
            "Type it into the Nura app to sign in.",
            "The code works for 10 minutes.",
            "Nura will never call you to ask for it.",
        ),
        # The message when someone else — the daughter setting him up — asked for it.
        "phone_code_on_behalf": (
            "Your Nura code is {code}.",
            "{who} asked for this code, to sign you in.",
            "Type it into the Nura app.",
            "The code works for 10 minutes.",
            "If you did not expect this, call {who} first.",
        ),
        # Beside a field on a review card that Nura could not read (E02-02).
        "could_not_read": ("Nura could not read this.", "Please type it."),
        # On a card for a page that is not a health paper: a receipt (E02-03).
        "not_a_health_paper": ("This does not look like a health paper.",),
        # On a card for a photo sent as a machine screen that is not one (E02-08).
        "not_a_machine_screen": ("This does not look like the screen of a machine.",),
        # On a card for a kind of photo Nura never looked at, distinct from a page it
        # looked at and could not read (E02-02): retaking it would fail again the same way.
        "photo_kind_not_read": (
            "Nura cannot open this kind of photo.",
            "Please type in what the paper says instead.",
        ),
        # Under a voice note Nura could not hear; the recording is kept (E02-06).
        "could_not_hear": ("Nura could not hear this note.", "Nura kept the note."),
    },
    "ms": {
        "code_works_for": ("Kod ini boleh digunakan selama 10 minit.",),
        "phone_code_self": (
            "Kod Nura anda ialah {code}.",
            "Taip kod ini dalam aplikasi Nura untuk daftar masuk.",
            "Kod ini boleh digunakan selama 10 minit.",
            "Nura tidak akan menelefon anda untuk meminta kod ini.",
        ),
        "phone_code_on_behalf": (
            "Kod Nura anda ialah {code}.",
            "{who} minta kod ini untuk daftar masuk bagi pihak anda.",
            "Taip kod ini dalam aplikasi Nura.",
            "Kod ini boleh digunakan selama 10 minit.",
            "Jika anda tidak menjangka mesej ini, telefon {who} dahulu.",
        ),
        "could_not_read": ("Nura tidak dapat membaca ini.", "Sila taip."),
        "not_a_health_paper": ("Ini tidak kelihatan seperti surat kesihatan.",),
        "not_a_machine_screen": ("Ini tidak kelihatan seperti skrin mesin.",),
        "photo_kind_not_read": (
            "Nura tidak dapat membuka jenis gambar ini.",
            "Sila taip apa yang tertulis pada kertas itu.",
        ),
        "could_not_hear": ("Nura tidak dapat mendengar nota ini.", "Nura sudah simpan nota ini."),
    },
    "zh": {
        "code_works_for": ("验证码在 10 分钟内有效。",),
        "phone_code_self": (
            "您的 Nura 验证码是 {code}。",
            "请在 Nura 应用里输入它来登录。",
            "验证码在 10 分钟内有效。",
            "Nura 绝不会打电话向您要验证码。",
        ),
        "phone_code_on_behalf": (
            "您的 Nura 验证码是 {code}。",
            "{who}要了这个验证码，帮您登录。",
            "请在 Nura 应用里输入它。",
            "验证码在 10 分钟内有效。",
            "如果您没想到会收到这个，请先打电话给{who}。",
        ),
        "could_not_read": ("Nura 看不清这个。", "请把它打出来。"),
        "not_a_health_paper": ("这看起来不像健康文件。",),
        "not_a_machine_screen": ("这看起来不像机器的屏幕。",),
        "photo_kind_not_read": (
            "Nura 无法打开这种照片。",
            "请改为手动输入纸上的内容。",
        ),
        "could_not_hear": ("Nura 听不清这段录音。", "Nura 保存了这段录音。"),
    },
}
"""Every line, by key, in each language Nura speaks."""


def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def lines(key: str, language: str | None = None) -> Lines:
    """The lines filed under `key`, in `language` (English when Nura does not speak it)."""
    return TEXT[language_of(language)][key]


CODE_WORKS_FOR = lines("code_works_for")[0]
PHONE_CODE_SELF = lines("phone_code_self")
PHONE_CODE_ON_BEHALF = lines("phone_code_on_behalf")
COULD_NOT_READ = lines("could_not_read")
NOT_A_HEALTH_PAPER = lines("not_a_health_paper")
NOT_A_MACHINE_SCREEN = lines("not_a_machine_screen")
COULD_NOT_HEAR = lines("could_not_hear")


def phone_code_message(
    code: str, *, asked_by: str | None = None, language: str | None = None
) -> str:
    """The text a phone receives with its six digits, for the person or on his behalf, in
    his language when the caller knows it (English otherwise)."""
    key = "phone_code_self" if asked_by is None else "phone_code_on_behalf"
    return "\n".join(lines(key, language)).format(code=code, who=asked_by or "")


# --- demo mode (ADR 0008) --------------------------------------------------------------------
# A demo deployment says so on every page it serves, in the person's language. The web client
# carries the same words in web/src/strings; these are the printable card's.

# @patient headline
DEMO_HEADLINE: dict[str, str] = {
    "en": "Demo — not for real health information",
    "ms": "Demo — bukan untuk maklumat kesihatan sebenar",
    "zh": "演示版 — 不用于真实的健康信息",
}

# @patient
DEMO_LINES: dict[str, tuple[str, ...]] = {
    "en": (
        "This is a demo.",
        "Do not put real health information in it.",
        "Everything here is wiped each night.",
    ),
    "ms": (
        "Ini ialah demo.",
        "Jangan masukkan maklumat kesihatan sebenar.",
        "Semua di sini dipadam setiap malam.",
    ),
    "zh": ("这是演示版。", "请不要输入真实的健康信息。", "这里的一切每晚都会清除。"),
}

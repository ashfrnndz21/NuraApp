"""What closing his account means, in his words (#143): the lines the confirm step shows, and
that his yes binds to (`app.drafts.CloseDraft`). Awaiting counsel's sign-off, with the
retention window (`docs/trust/account-closure.md`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.channels.strings import language_of
from app.medicines.strings import say_date

# @patient
CLOSING: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Nura will stop keeping your papers.",
        "Your family will not be told when you are unwell.",
        "Nobody can open your papers from now on.",
        "Your papers will be deleted on {day}.",
        "Until then, you can change your mind.",
    ),
    "ms": (
        "Nura akan berhenti menyimpan surat-surat anda.",
        "Keluarga anda tidak akan diberitahu apabila anda tidak sihat.",
        "Tiada sesiapa boleh buka surat-surat anda mulai sekarang.",
        "Surat-surat anda akan dipadam pada {day}.",
        "Sebelum itu, anda boleh ubah fikiran.",
    ),
    "zh": (
        "Nura 会停止保存您的文件。",
        "您不舒服时，不会再通知您的家人。",
        "从现在起，谁都不能打开您的文件。",
        "您的文件会在{day}删除。",
        "在那之前，您可以改变主意。",
    ),
}
"""What stops, what is no longer told, and the day his papers go, in that order."""


def closing_lines(language: str | None, delete_on: date) -> tuple[str, ...]:
    code = language_of(language)
    return tuple(line.format(day=say_date(delete_on, code)) for line in CLOSING[code])

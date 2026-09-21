"""`app.search.elapsed`: how long ago, computed, never guessed by the model
(`app.llm.ask_agent`'s fix — the model must not do date arithmetic). Digits, never number
words (`docs/plain-words.md` rule 10): the owner's own acceptance line said "about twenty
months ago"; this always says "about 20 months ago" for the same gap.
"""

from __future__ import annotations

import pytest

from app.safety.plain_words import verify
from app.search.elapsed import elapsed_days

# Boundary days named in the brief: 0, 1, 6, 7, 13, 14, 29, 30, 59, 60, 364, 365, 800, plus a
# future gap.
_EN_BOUNDARIES: dict[int, str] = {
    0: "today",
    1: "yesterday",
    6: "6 days ago",
    7: "7 days ago",
    13: "13 days ago",
    14: "about 2 weeks ago",
    29: "about 4 weeks ago",
    30: "about 1 month ago",
    59: "about 2 months ago",
    60: "about 2 months ago",
    364: "about 12 months ago",
    365: "about 12 months ago",
    800: "about 2 years ago",
}


@pytest.mark.parametrize("days,expected", sorted(_EN_BOUNDARIES.items()))
def test_elapsed_days_boundaries_english(days: int, expected: str) -> None:
    assert elapsed_days(days, "en") == expected


def test_elapsed_days_future_is_in_not_ago() -> None:
    assert elapsed_days(-3, "en") == "in 3 days"


def test_elapsed_days_the_owners_own_example_says_twenty_months_in_digits() -> None:
    """The acceptance line for this feature: "Your last blood test was on 21 January 2025,
    about twenty months ago" (asked 2026-09-21, about 608 days). Rule 10 says digits, so this
    says "20", not "twenty" — the fix keeps the owner's shape and the rule's letter both."""
    assert elapsed_days(608, "en") == "about 20 months ago"


def test_a_608_day_gap_is_still_months_not_years() -> None:
    """The month bucket must reach far enough that a ~20-month gap is not rounded up into
    "about 2 years ago" — that would contradict the owner's own acceptance wording."""
    phrase = elapsed_days(608, "en")
    assert "month" in phrase
    assert "year" not in phrase


def test_elapsed_days_boundaries_malay() -> None:
    assert elapsed_days(0, "ms") == "hari ini"
    assert elapsed_days(1, "ms") == "semalam"
    assert elapsed_days(9, "ms") == "9 hari lalu"
    assert elapsed_days(21, "ms") == "kira-kira 3 minggu lalu"
    assert elapsed_days(608, "ms") == "kira-kira 20 bulan lalu"
    assert elapsed_days(800, "ms") == "kira-kira 2 tahun lalu"
    assert elapsed_days(-3, "ms") == "dalam 3 hari"


def test_elapsed_days_boundaries_chinese() -> None:
    assert elapsed_days(0, "zh") == "今天"
    assert elapsed_days(1, "zh") == "昨天"
    assert elapsed_days(9, "zh") == "9天前"
    assert elapsed_days(21, "zh") == "大约3周前"
    assert elapsed_days(608, "zh") == "大约20个月前"
    assert elapsed_days(800, "zh") == "大约2年前"
    assert elapsed_days(-3, "zh") == "3天后"


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
@pytest.mark.parametrize("days", [0, 1, 6, 7, 9, 13, 14, 21, 29, 30, 59, 60, 364, 365, 608, 800])
def test_every_elapsed_phrase_is_plain_words_clean(language: str, days: int) -> None:
    """Not itself a whole patient line (it fills a slot in one), but its words must still be
    his: no fail-severity finding at the `phrase` profile."""
    phrase = elapsed_days(days, language)
    findings = verify(phrase, language, "phrase")
    assert not any(f.severity == "fail" for f in findings), (phrase, findings)

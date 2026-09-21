"""How long ago, in his own words — computed here, never guessed by a model.

`app.llm.ask_agent.ClaudeAsker` hands the model dated items (readings, visits, medicines,
papers, and now papers still waiting to be checked), and the live defect this fixes is the
model doing its own date arithmetic mid-answer instead of reading what it was given. The fix:
every dated tool line carries its elapsed phrase already computed, on the app's own clock
(`app.clock`, read through `app.db.utcnow` — never `datetime.now()` directly, so a frozen
clock in a dev run or a test is honoured the same way every other timestamp in this app is),
and the prompt tells the model to use the phrase given, verbatim, never work it out itself.

Digits, never number words (`docs/plain-words.md` rule 10). The owner's own acceptance line
for this feature said "about twenty months ago" — but rule 10 is unchanged for Ask, so this
always answers "about 20 months ago": the shape of his sentence, the letter of the rule.

The buckets, chosen so the owner's own example lands correctly and stays legible at every
scale: exact days up to two weeks ("9 days ago"), then weeks up to a month, then months up to
about two years (a 608-day gap says "about 20 months ago", not "about 2 years ago" — the
owner's own words for it), then years beyond that. A future date (a coming visit) is said the
same way, "in" instead of "ago"."""

from __future__ import annotations

from datetime import date

_DAY_BUCKET_MAX = 13
_WEEK_BUCKET_MAX = 29
_MONTH_BUCKET_MAX = 729
"""About two years: past this, a gap is said in years, not months (a 608-day gap, the owner's
own "about twenty months", stays inside the month bucket; an 800-day one is "about 2 years")."""

_WORDS: dict[str, dict[str, str]] = {
    "en": {
        "today": "today",
        "yesterday": "yesterday",
        "tomorrow": "tomorrow",
        "days_ago": "{n} days ago",
        "in_days": "in {n} days",
        "week_ago": "about 1 week ago",
        "weeks_ago": "about {n} weeks ago",
        "in_week": "in about 1 week",
        "in_weeks": "in about {n} weeks",
        "month_ago": "about 1 month ago",
        "months_ago": "about {n} months ago",
        "in_month": "in about 1 month",
        "in_months": "in about {n} months",
        "year_ago": "about 1 year ago",
        "years_ago": "about {n} years ago",
        "in_year": "in about 1 year",
        "in_years": "in about {n} years",
    },
    "ms": {
        "today": "hari ini",
        "yesterday": "semalam",
        "tomorrow": "esok",
        "days_ago": "{n} hari lalu",
        "in_days": "dalam {n} hari",
        "week_ago": "kira-kira 1 minggu lalu",
        "weeks_ago": "kira-kira {n} minggu lalu",
        "in_week": "dalam kira-kira 1 minggu",
        "in_weeks": "dalam kira-kira {n} minggu",
        "month_ago": "kira-kira 1 bulan lalu",
        "months_ago": "kira-kira {n} bulan lalu",
        "in_month": "dalam kira-kira 1 bulan",
        "in_months": "dalam kira-kira {n} bulan",
        "year_ago": "kira-kira 1 tahun lalu",
        "years_ago": "kira-kira {n} tahun lalu",
        "in_year": "dalam kira-kira 1 tahun",
        "in_years": "dalam kira-kira {n} tahun",
    },
    "zh": {
        "today": "今天",
        "yesterday": "昨天",
        "tomorrow": "明天",
        "days_ago": "{n}天前",
        "in_days": "{n}天后",
        "week_ago": "大约1周前",
        "weeks_ago": "大约{n}周前",
        "in_week": "大约1周后",
        "in_weeks": "大约{n}周后",
        "month_ago": "大约1个月前",
        "months_ago": "大约{n}个月前",
        "in_month": "大约1个月后",
        "in_months": "大约{n}个月后",
        "year_ago": "大约1年前",
        "years_ago": "大约{n}年前",
        "in_year": "大约1年后",
        "in_years": "大约{n}年后",
    },
}


def _bucket(words: dict[str, str], unit: str, count: int, future: bool) -> str:
    if count <= 1:
        return words[f"in_{unit}" if future else f"{unit}_ago"]
    key = f"in_{unit}s" if future else f"{unit}s_ago"
    return words[key].format(n=count)


def elapsed_days(days: int, language: str = "en") -> str:
    """The elapsed phrase for a gap of `days` (positive: in the past; negative: in the
    future), in `language`. Pure, no clock read here — the caller already computed the gap
    against the one clock (`app.db.utcnow`)."""
    words = _WORDS.get(language, _WORDS["en"])
    n = abs(days)
    future = days < 0
    if n == 0:
        return words["today"]
    if n == 1:
        return words["tomorrow"] if future else words["yesterday"]
    if n <= _DAY_BUCKET_MAX:
        return words["in_days" if future else "days_ago"].format(n=n)
    if n <= _WEEK_BUCKET_MAX:
        return _bucket(words, "week", round(n / 7), future)
    if n <= _MONTH_BUCKET_MAX:
        return _bucket(words, "month", round(n / 30), future)
    return _bucket(words, "year", round(n / 365), future)


def elapsed_phrase(reference: date, target: date, language: str = "en") -> str:
    """How long before (or after) `reference` `target` fell, in his words. `reference` is
    always today on the app's own clock (`app.delivery.timeline_strings.day_of(utcnow(), ...)`
    in the caller), never a caller-supplied "now"."""
    return elapsed_days((reference - target).days, language)


__all__ = ["elapsed_days", "elapsed_phrase"]

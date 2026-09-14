"""The plain-words verifier: the glossary examples pass, the fragment examples fail (E22-01).

The doc is the spec, so its glossary is read from `docs/plain-words.md` at test time: every
word in the "Instead of" column fails, every entry in the "Say" column passes. Then one
positive and one negative per rule, the detectors, the template fillers, and the discovery of
tagged strings in the source — including the ones already on main, so nothing can be untagged
without this test noticing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.safety.plain_words import (
    Finding,
    check_files,
    check_repo,
    fill,
    filler_for,
    main,
    patient_files,
    patient_paths,
    repo_root,
    strings_in,
    strings_in_python,
    strings_in_xcstrings,
    tagged_statements,
    verify,
)

ROOT = repo_root()
DOC = (ROOT / "docs" / "plain-words.md").read_text(encoding="utf-8")


def failures(text: str, language: str = "en", kind: str = "line") -> list[Finding]:
    return [f for f in verify(text, language, kind) if f.severity == "fail"]  # type: ignore[arg-type]


def rules(text: str, language: str = "en", kind: str = "line") -> set[int]:
    return {f.rule for f in failures(text, language, kind)}


# --- the glossary, read from the doc -------------------------------------------------------------


def glossary_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in DOC.splitlines():
        if not line.startswith("|") or line.startswith(("| Instead of", "|---")):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 2:
            rows.append((cells[0], cells[1]))
    return rows


def red_terms() -> list[str]:
    terms: list[str] = []
    for instead, _ in glossary_rows():
        for term in re.split(r",\s*|\s*/\s*", instead):
            terms.append(term.strip())
    return terms


def say_entries() -> list[str]:
    return [re.sub(r"[\"“”]", "", say).strip() for _, say in glossary_rows()]


def test_the_glossary_was_found_in_the_doc() -> None:
    assert len(glossary_rows()) >= 29
    assert ("Metformin", "The sugar tablet") in glossary_rows()


@pytest.mark.parametrize("term", red_terms())
def test_every_red_word_in_the_glossary_fails(term: str) -> None:
    if term.lower() == "saved":
        # The row lists it, but the Say column says "Saved." — a word the doc tells us to say
        # cannot be banned. The other two words of the row ("logged", "filed") are red.
        assert not failures(term, kind="phrase")
        return
    found = failures(term, kind="phrase")
    assert found, term
    assert {f.rule for f in found} <= {4, 11, 12, 13}, term


@pytest.mark.parametrize("say", say_entries())
def test_every_plain_phrase_in_the_glossary_passes(say: str) -> None:
    assert not failures(say, kind="phrase"), [str(f) for f in failures(say, kind="phrase")]


def test_the_rewrite_is_the_plain_phrase() -> None:
    (finding,) = failures("Take the furosemide tonight.")
    assert finding.rule == 4
    assert "the water pill" in finding.rewrite


def test_a_chemical_name_may_stand_second_but_never_alone() -> None:
    assert not failures("Take the water pill (furosemide) tonight.")
    assert rules("Take the furosemide tonight.") == {4}
    assert not failures("A body salt. Doctors call it potassium.", kind="phrase")
    assert rules("Your potassium is high.") == {4}


# --- rule 1: plain is not clipped -----------------------------------------------------------------

FRAGMENTS = ["A heart doctor explains.", "Only the part for you.", "30 seconds."]
WHOLE = [
    "A heart doctor talks about the water pill and bananas.",
    "It is 30 seconds long.",
    "Every morning, stand on the scale before breakfast.",
    "Ash will book it.",
    "Mei will pick you up at 9.",
    "Water is OK.",
    "It is not a worry.",
    "This number only goes up.",
    "One tablet was late.",
    "Is the water pill bad for my kidneys?",
    "When you see the doctor, Nura listens.",
    "We kept only the part that matters for you.",
    "Nura keeps what you and the doctor say.",
]


@pytest.mark.parametrize("fragment", FRAGMENTS)
def test_the_docs_fragment_examples_fail(fragment: str) -> None:
    assert 1 in rules(fragment), fragment


def test_the_three_fragments_on_one_line_are_three_ideas() -> None:
    clipped = "A heart doctor explains. Only the part for you. 30 seconds."
    assert rules(clipped) == {2}
    assert all(1 in rules(piece) for piece in failures(clipped)[0].rewrite.split(" / "))


@pytest.mark.parametrize("sentence", WHOLE)
def test_the_docs_whole_sentences_pass(sentence: str) -> None:
    assert not failures(sentence), [str(f) for f in failures(sentence)]


def test_a_verb_that_needs_an_object_stops_the_sentence_short() -> None:
    (finding,) = failures("A heart doctor explains.")
    assert "what?" in finding.problem


def test_a_small_letter_or_no_full_stop_is_not_a_whole_line() -> None:
    assert rules("the water pill is ready.") == {1}
    assert rules("The water pill is ready") == {1}
    assert not failures("Ash can see these parts:")


def test_a_phrase_is_not_asked_to_be_a_sentence() -> None:
    assert rules("your papers") == {1}
    assert not failures("your papers", kind="phrase")
    assert not failures("Keeping your papers", kind="headline")
    assert not failures("# What you said yes to")


# --- rule 2: one idea per line ------------------------------------------------------------------


def test_two_sentences_on_one_line_are_two_ideas() -> None:
    (finding,) = failures("Ash will book it. Mei will pick you up at 9.")
    assert finding.rule == 2
    assert finding.rewrite == "Ash will book it. / Mei will pick you up at 9."
    assert rules("Ash will book it; Mei will drive.") == {2}
    assert not failures("Ash will book it.\nMei will pick you up at 9.")


def test_two_ideas_in_chinese() -> None:
    assert rules("您可以随时停止。您的药在这里。", language="zh") == {2}
    assert not failures("您可以随时停止。", language="zh")


# --- rule 3: short words, short lines -------------------------------------------------------------


def test_over_fifteen_words_fail_and_over_ten_is_a_note() -> None:
    fifteen = "Nura will ask you to say yes again the next time you open the app."
    assert not failures(fifteen)
    assert [f.severity for f in verify(fifteen)] == ["note"]
    twenty = (
        "Nura will ask you to say yes again the next time you open the app on your phone at home."
    )
    assert rules(twenty) == {3}


def test_a_long_word_he_would_ask_about_fails_but_his_long_words_do_not() -> None:
    assert rules("Your medication is ready.") == {3}
    assert rules("The cardiologist will call.") == {3}
    assert not failures("Your emergency card is ready.")
    assert not failures("Everything is in Singapore.")
    assert not failures("Gleneagles is on your insurance.")


# --- rule 5: the day and the date -----------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "Come on 14/09.",
        "Come on 2026-09-14.",
        "Come at 09:00.",
        "Come at 09:00 UTC.",
        "Come on the 29th.",
        "Come on 29 September.",
        "Come on Sept 29.",
        "Come on Mon 29 September.",
    ],
)
def test_dates_and_times_not_in_his_form_fail(bad: str) -> None:
    assert 5 in rules(bad), bad


def test_the_day_and_the_date_pass() -> None:
    assert not failures("Come on Monday 29 September.")
    assert not failures("Monday 29 September", kind="phrase")
    assert not failures("Thursday at 10", kind="phrase")
    assert not failures("Mei will pick you up on Monday 14 September 2026.")
    assert not failures("Nura made this page for you on Monday 14 September 2026.")


# --- rules 6 and 7: what to do and when, who does the next thing ---------------------------------


def test_an_action_card_names_who_does_the_next_thing() -> None:
    assert not failures("Ash will book it.", kind="action")
    assert not failures("Nura will send it tonight.", kind="action")
    assert not failures("Dr Tan will see you on Monday 29 September.", kind="action")
    assert rules("It will be booked.", kind="action") == {7}
    assert 7 not in rules("It will be booked.")


def test_an_instruction_says_when() -> None:
    assert not failures("Every morning, stand on the scale before breakfast.", kind="action")
    assert rules("Keep weighing.", kind="action") == {6}
    assert not failures("Keep weighing.")


# --- rule 10: numbers as digits, small and few ----------------------------------------------------


def test_numbers_are_digits() -> None:
    (finding,) = failures("The code works for ten minutes.")
    assert finding.rule == 10
    assert finding.rewrite == "The code works for 10 minutes."
    assert not failures("One tablet was late.")
    assert not failures("6 days out of 7.", kind="phrase")
    assert rules("Take 2 at 8, 1 at 12 and 2 at 6.") == {10}


# --- rules 11 and 12: red words, nothing to decode ------------------------------------------------


@pytest.mark.parametrize("word", ["missed", "failed", "overdue", "non-compliant"])
def test_the_red_words_fail(word: str) -> None:
    assert rules(f"One tablet was {word}.") == {11}


@pytest.mark.parametrize("word", ["dose", "recheck", "follow-up", "flag", "log"])
def test_the_words_he_would_have_to_decode_fail(word: str) -> None:
    assert rules(f"Your {word} is on Monday 29 September.") == {12}


def test_abbreviations_and_units_fail_but_his_own_do_not() -> None:
    assert rules("Your BP is 148.") == {12}
    assert rules("Nura keeps your PDPA papers.") == {12}
    assert rules("Take 40 mg tonight.") == {12}
    assert rules("Your sugar is 7 mmol/L.") == {12}
    assert rules("Bring your papers, e.g. the letter.") == {12}
    assert not failures("Water is OK.")
    assert not failures("Bring your IC.")
    assert not failures("You are 1 kg lighter.")


# --- identifiers ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "Your id is 6f2c4a1e-9b3d-4c7a-8e2f-1a2b3c4d5e6f.",
        "Call +65 9123 4567 now.",
        "Your IC is S1234567D.",
        "Your IC is 560314-08-1234.",
        "Write to pa@example.com now.",
        "Your code is 0123456789abcdef0123.",
    ],
)
def test_identifiers_never_reach_him(bad: str) -> None:
    assert 12 in rules(bad), bad


def test_a_short_code_is_not_an_identifier() -> None:
    assert not failures("Your Nura code is 481302.")


# --- rule 13: the same words every time ---------------------------------------------------------


def test_variants_of_his_words_fail() -> None:
    assert rules("Write it in the log.") == {13}
    assert rules("Bring your discharge summary.") == {13}
    assert rules("Call the clinic.") == {13}
    assert not failures("Write it in your blood pressure book.")


def test_his_own_record_is_allowed_but_the_record_is_not() -> None:
    assert not failures("The papers Nura already has stay in your record.")
    assert not failures("You are letting Ash see some of your record.")
    assert rules("Nura saved it to the record.") == {13}
    assert rules("Nura keeps a record.") == {4}


# --- languages ------------------------------------------------------------------------------------


def test_english_rules_are_skipped_for_malay_and_chinese() -> None:
    malay = "Anda membenarkan Ash melihat sebahagian daripada rekod anda."
    assert rules(malay) >= {3}  # "membenarkan" read as English
    assert not failures(malay, language="ms")
    assert not failures("您可以随时叫 Nura 停下来。", language="en")  # the script decides


def test_what_is_still_checked_in_every_language() -> None:
    assert rules("Ambil furosemide anda pada 14/09.", language="ms") == {4, 5}
    assert rules("请在 09:00 服用 metformin。", language="zh") == {4, 5}
    assert rules("Anda boleh berhenti pada bila-bila masa", language="ms") == {1}
    assert rules("您可以随时停止", language="zh") == {1}
    assert rules("Nombor anda ialah S1234567D.", language="ms") == {12}


# --- templates ------------------------------------------------------------------------------------


def test_slots_are_filled_with_representative_values() -> None:
    assert filler_for("name") == "Ash"
    assert filler_for("given_at_plain") == "Monday 14 September"
    assert filler_for("count") == "2"
    assert filler_for("me") == "you"
    assert filler_for("something_else") == "Ash"
    assert fill("{who} asked for this code on {date}, {n} times.") == (
        "Ash asked for this code on Monday 14 September, 2 times."
    )
    assert fill("{{not a slot}}") == "{not a slot}"


def test_templates_pass_or_fail_as_their_filled_lines_would() -> None:
    assert not failures("Your Nura code is {code}.")
    assert not failures("{name} can see them until you say stop.")
    assert not failures("Nura made this page for {who} on {prepared_at_plain}.")
    assert rules("{name} logged it on {date}.") == {12}


def test_the_finding_points_at_the_source_line_of_a_multi_line_text() -> None:
    found = failures("Ash will book it.\nYour dose is ready.\nWater is OK.")
    assert [(f.offset, f.rule) for f in found] == [(1, 12)]
    assert found[0].text == "Your dose is ready."
    assert str(found[0]).startswith("rule 12 — ")


def test_kind_is_checked() -> None:
    with pytest.raises(ValueError):
        verify("Water is OK.", kind="poem")  # type: ignore[arg-type]


# --- finding the strings in the source ------------------------------------------------------------

SOURCE = '''"""A module whose docstring mentions strings tagged `@patient`; that is not a tag."""

# @patient
GREETING = "Nura made this page for you."
WORDS = {"en": "your papers", "ms": "surat-surat anda"}  # @patient phrase
CODE_WORKS = "The code works for 10 minutes."
"""@patient The one line every message shares."""
TITLES = {"hold": "Keeping your papers"}
"""@patient headline The heading over each purpose."""
NOT_TAGGED = "This string has a dose in it."
TEXTS = (
    Text("1", "ms", "Anda membenarkan Ash melihat."),
    Text("1", "en", "You choose. You see. You stop."),  # plain-words: history, not shown
    Text("2", "en", "You can stop this at any time."),
)
"""@patient"""


# @patient
def build(name: str, entry: dict[str, str]) -> str:
    """The docstring is not patient text, dose and all."""
    status = "out_of_date"
    if entry["status"] == "withdrawn":
        raise ValueError("a log message, with a dose")
    assert status, "an assertion, with a dose"
    lines = [f"- {name}", f"{name} can see these parts:", f"{name} said yes on {entry['given_at_plain']}."]
    return "\\n".join(lines).replace("dose", "x")


class Page:
    # @patient
    @property
    def title(self) -> str:
        return f"# What {self.me} said yes to"
'''


def found_texts(source: str) -> dict[str, tuple[str, str, int]]:
    return {
        s.text: (s.language, s.kind, s.line) for s in strings_in_python(Path("fixture.py"), source)
    }


def test_every_tag_form_is_found_with_its_kind_and_language() -> None:
    found = found_texts(SOURCE)
    assert found["Nura made this page for you."] == ("en", "line", 4)
    assert found["your papers"] == ("en", "phrase", 5)
    assert found["surat-surat anda"] == ("ms", "phrase", 5)
    assert found["The code works for 10 minutes."] == ("en", "line", 6)
    assert found["Keeping your papers"] == ("en", "headline", 8)
    assert found["Anda membenarkan Ash melihat."] == ("ms", "line", 12)
    assert found["You can stop this at any time."] == ("en", "line", 14)
    assert found["# What {me} said yes to"] == ("en", "line", 34)


def test_code_positions_and_untagged_strings_are_not_patient_text() -> None:
    found = found_texts(SOURCE)
    assert "This string has a dose in it." not in found
    assert not any(
        "docstring" in text or "assertion" in text or "log message" in text for text in found
    )
    assert not any(
        text in ("out_of_date", "withdrawn", "status", "dose", "x", "1", "2") for text in found
    )
    assert "- {name}" not in found  # nothing but a slot
    assert "The one line every message shares." not in found  # the tag itself


def test_f_strings_are_templates_with_named_slots() -> None:
    found = found_texts(SOURCE)
    assert found["{name} can see these parts:"] == ("en", "line", 26)
    assert found["{name} said yes on {given_at_plain}."] == ("en", "line", 26)


def test_history_is_exempt_and_counted(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture_history.py"
    fixture.write_text(SOURCE, encoding="utf-8")
    report = check_files([fixture])
    assert report.exempt == 1
    assert report.ok, [str(f) for f in report.failures]
    assert "You choose. You see. You stop." not in {f.text for f in report.findings}
    assert "1 exempt as history" in report.summary()


def test_tagged_statements_carry_the_kind() -> None:
    kinds = sorted(kind for _, kind in tagged_statements(SOURCE))
    assert kinds == ["headline", "line", "line", "line", "line", "line", "phrase"]


def test_the_strings_catalogue_is_read_by_comment_tag(tmp_path: Path) -> None:
    catalogue = {
        "sourceLanguage": "en",
        "strings": {
            "Your water pill is ready.": {
                "comment": "patient",
                "localizations": {
                    "en": {
                        "stringUnit": {"state": "translated", "value": "Your water pill is ready."}
                    },
                    "ms": {
                        "stringUnit": {"state": "translated", "value": "Pil air anda sudah siap."}
                    },
                },
            },
            "Take your dose now.": {
                "comment": "patient action — the Now card",
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "Take your dose now."}}
                },
            },
            "Settings": {"comment": "caregiver", "localizations": {}},
        },
    }
    path = tmp_path / "Localizable.xcstrings"
    path.write_text(json.dumps(catalogue, indent=2), encoding="utf-8")
    found = strings_in_xcstrings(path)
    assert {(s.text, s.language, s.kind) for s in found} == {
        ("Your water pill is ready.", "en", "line"),
        ("Pil air anda sudah siap.", "ms", "line"),
        ("Take your dose now.", "en", "action"),
    }
    report = check_files([path])
    assert {f.rule for f in report.failures} == {12}


def test_a_plain_text_file_is_checked_line_by_line(tmp_path: Path) -> None:
    memo = tmp_path / "memo.txt"
    memo.write_text("Ash will book it.\n\nYour dose is ready.\n", encoding="utf-8")
    assert [(s.line, s.text) for s in strings_in(memo)] == [
        (1, "Ash will book it."),
        (3, "Your dose is ready."),
    ]
    report = check_files([memo])
    assert [(f.line, f.rule) for f in report.failures] == [(3, 12)]


# --- the repository -------------------------------------------------------------------------------


def test_the_paths_come_from_the_rules_files_front_matter() -> None:
    paths = patient_paths(
        (ROOT / ".claude" / "rules" / "patient-strings.md").read_text(encoding="utf-8")
    )
    assert paths == [
        "backend/app/delivery/**",
        "backend/app/channels/**",
        "backend/app/consent/**",
        "ios/Nura/**",
    ]
    assert patient_paths("no front matter") == []


def test_mains_tagged_strings_are_still_found() -> None:
    """Every tag on main is still a tag, so no string can be untagged without this failing."""
    files = patient_files(ROOT)
    assert {p.name for p in files} >= {"texts.py", "export.py", "strings.py", "service.py"}
    tags = sum(
        len(tagged_statements(p.read_text(encoding="utf-8"))) for p in files if p.suffix == ".py"
    )
    assert tags >= 17
    found = [s for p in files for s in strings_in(p)]
    assert len(found) >= 140
    assert {s.language for s in found} >= {"en", "ms", "zh"}
    assert {s.kind for s in found} >= {"line", "phrase", "headline"}


def test_every_patient_string_in_the_repository_passes() -> None:
    """`make plain-words` exits 0: the acceptance line for the strings already here."""
    report = check_repo(ROOT)
    assert report.strings >= 140
    assert report.ok, [str(f) for f in report.failures]


# --- the command line -----------------------------------------------------------------------------


def test_the_command_fails_on_a_fragment_and_passes_a_whole_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--text", "A heart doctor explains."]) == 1
    out = capsys.readouterr().out
    assert "rule 1 — " in out and "1 failures" in out
    assert main(["--text", "Water is OK."]) == 0
    assert main(["--text", "Ash will book it.", "--kind", "action"]) == 0
    assert main(["--text", "Anda boleh berhenti pada bila-bila masa.", "--lang", "ms"]) == 0


def test_the_command_reports_a_file_with_path_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "fixture_cli.py"
    fixture.write_text('# @patient\nLINE = "Your dose is on 14/09."\n', encoding="utf-8")
    assert main(["--only", str(fixture)]) == 1
    out = capsys.readouterr().out
    assert f"{fixture}:2: rule 5 — " in out
    assert f"{fixture}:2: rule 12 — " in out
    assert main(["--only", "--json", str(fixture)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["strings"] == 1
    assert sorted(f["rule"] for f in payload["failures"]) == [5, 12]
    assert payload["failures"][0]["line"] == 2


def test_the_command_explains_the_rules(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--explain"]) == 0
    out = capsys.readouterr().out
    assert "docs/plain-words.md" in out
    assert all(f"\n  {n} " in out or f"\n  {n}  " in out for n in range(1, 14))


def test_the_command_over_the_repository_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "0 failures" in capsys.readouterr().out

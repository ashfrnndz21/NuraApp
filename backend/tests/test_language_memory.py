"""The glossary and the translation memory (E22-02): the same words every time.

The acceptance line is "term consistency enforced across cards, voice and WhatsApp". The
cards, the WhatsApp replies and templates and the web client are all catalogues in the
memory; the voice is the cards' lines said (`test_voice_script.py`). So the test is that the
repository passes the checker, and that the checker fails what it should, on small catalogues
of its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.language import glossary as glossary_module
from app.language import memory as memory_module
from app.language.glossary import parse
from app.language.memory import (
    Memory,
    build,
    check,
    check_repo,
    normal,
    parent_of,
)
from app.safety.plain_words import repo_root

ROOT = repo_root()

DOC = """# Plain words

## 1. The rules

13. **The same words every time.** Once it's "your blood pressure book", it is never "the log", "the readings", or "the record".

---

## 2. Glossary

| Instead of | Say |
|---|---|
| Diuretic, furosemide | The water pill |
| Reading, log | Your blood pressure. Your blood pressure book. |
| Flag, alert, triage | "This one we do not wait for." |

---

## 6. The same words in Malay and Chinese

| English | Malay | Chinese | Never |
|---|---|---|---|
| water pill | pil air | 去水药 | |
| hospital letter | surat hospital | 出院信 | zh "医院信" |
| This one we do not wait for | yang ini kita tidak tunggu | 这个我们不等 | zh "这个不能等" |
| your papers | surat-surat anda | 文件 | en "your record"; ms "rekod" |
"""


# --- the glossary --------------------------------------------------------------------------------


def test_the_glossary_is_read_row_by_row() -> None:
    g = parse(DOC)
    assert g.rows[0].instead_of == ("diuretic", "furosemide")
    assert g.rows[0].say == ("The water pill",)
    assert g.rows[1].say == ("Your blood pressure", "Your blood pressure book")
    assert g.rows[2].say == ("This one we do not wait for.",)
    assert "furosemide" in g.red_words()


def test_rule_13_gives_his_word_and_the_variants_never_said() -> None:
    g = parse(DOC)
    assert g.same_words == (
        ("your blood pressure book", ("the log", "the readings", "the record")),
    )
    assert ("the log", "your blood pressure book") in list(g.never("en"))


def test_section_6_gives_each_thing_in_three_languages_and_the_words_never_said() -> None:
    g = parse(DOC)
    water = g.term("water pill")
    assert water is not None
    assert (water.say("en"), water.say("ms"), water.say("zh")) == (
        "water pill",
        "pil air",
        "去水药",
    )
    letter = g.term("hospital letter")
    assert letter is not None and letter.never == {"zh": ("医院信",)}
    assert ("医院信", "出院信") in list(g.never("zh"))
    assert ("rekod", "surat-surat anda") in list(g.never("ms"))
    assert ("your record", "your papers") in list(g.never("en"))


def test_the_repositorys_doc_carries_the_three_languages() -> None:
    """docs/plain-words.md is the seed: §2's glossary, rule 13, and §6 in Malay and Chinese."""
    g = glossary_module.load(ROOT)
    assert len(g.rows) >= 25
    assert g.same_words and g.same_words[0][0] == "your blood pressure book"
    for english, malay, chinese in (
        ("blood pressure tablet", "ubat tekanan darah", "血压药"),
        ("hospital letter", "surat hospital", "出院信"),
        ("This one we do not wait for", "yang ini kita tidak tunggu", "这个我们不等"),
    ):
        term = g.term(english)
        assert term is not None, english
        assert (term.say("ms"), term.say("zh")) == (malay, chinese)


# --- the memory, on the repository ---------------------------------------------------------------


@pytest.fixture(scope="module")
def repo() -> Memory:
    return build(ROOT)


def test_every_line_has_a_stable_id_of_catalogue_key_and_language(repo: Memory) -> None:
    ids = [entry.id for entry in repo.entries]
    assert len(ids) == len(set(ids))
    flag = repo.get("backend/app/delivery/strings:LINES.flag_family.1:zh")
    assert flag is not None and flag.text == "这个我们不等。"
    refused = repo.get("web/src/strings:refusals.OutOfScope:ms")
    assert refused is not None and refused.path == "web/src/strings/ms.ts"


def test_twins_share_everything_but_the_language(repo: Memory) -> None:
    group = repo.groups()[("backend/app/channels/whatsapp/strings", "RED_FLAG_OPENING")]
    assert {code: e.text for code, e in group.items()} == {
        "en": "This one we do not wait for.",
        "ms": "Yang ini kita tidak tunggu.",
        "zh": "这个我们不等。",
    }


def test_a_language_key_inside_a_language_key_is_part_of_the_key(repo: Memory) -> None:
    """`LANGUAGE_NAMES["ms"]["en"]` is the Malay for "English"."""
    malay = repo.get("backend/app/channels/safety_strings:LANGUAGE_NAMES.en:ms")
    assert malay is not None and malay.text == "Bahasa Inggeris"


def test_a_word_the_verifier_reads_as_a_token_is_still_his_word(repo: Memory) -> None:
    """ "demam" is a whole Malay word; filed under "ms" it is in the memory."""
    fever = repo.get("backend/app/reasoning/visits/strings:RED_FLAG_WORDS.fever_on_medicine:ms")
    assert fever is not None and fever.text == "demam"


def test_the_web_file_is_the_language(repo: Memory) -> None:
    """en.ts's `zh: "中文"` is the English file's name for Chinese, not a Chinese line."""
    english = repo.get("web/src/strings:me.zh:en")
    assert english is not None and english.text == "中文"


def test_a_rendered_line_is_matched_back_to_its_template(repo: Memory) -> None:
    found = [e.id for e in repo.match("Your blood pressure today was 138 over 84.", "en")]
    assert "backend/app/delivery/strings:LINES.reading.0:en" in found


def test_the_repository_passes(repo: Memory) -> None:
    """Every catalogue — the cards, the WhatsApp replies and templates, the web client — says
    one thing one way in every language. What cannot be edited in place (consent words, an
    approved template) is a note naming its follow-up, never a failure."""
    report = check_repo(ROOT)
    assert report.failures == [], "\n".join(str(f) for f in report.failures)
    for note in report.notes:
        assert "follow-up" in note.fix, str(note)


def test_the_red_flag_line_is_one_line_in_chinese_on_the_card_the_reply_and_the_notice(
    repo: Memory,
) -> None:
    said = {
        group["zh"].text
        for (catalogue, _), group in repo.groups().items()
        if catalogue != "backend/app/channels/whatsapp/templates"
        and "en" in group
        and "zh" in group
        and group["en"].text == "This one we do not wait for."
    }
    assert said == {"这个我们不等。"}


def test_the_hospital_letter_is_one_word_in_chinese(repo: Memory) -> None:
    assert not [e.id for e in repo.entries if "医院信" in e.text]
    assert any("出院信" in e.text for e in repo.entries)


# --- the checks, on catalogues of their own ------------------------------------------------------


def _catalogue(tmp_path: Path, relative: str, source: str) -> Path:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _report(tmp_path: Path, *files: tuple[str, str]) -> memory_module.Report:
    paths = [_catalogue(tmp_path, relative, source) for relative, source in files]
    return check(build(tmp_path, paths), parse(DOC))


def _checks(report: memory_module.Report) -> list[tuple[str, str]]:
    return [(f.check, f.severity) for f in report.findings]


def test_a_line_with_no_malay_or_chinese_twin_fails(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (
            "backend/app/cards/strings.py",
            '# @patient\nLINES = {"en": {"a": "Nura wrote it down."}, "zh": {"a": "Nura 记下了。"}}\n',
        ),
    )
    assert _checks(report) == [("twins", "fail")]
    assert "no Malay twin" in report.findings[0].problem


def test_twins_that_fill_other_slots_fail(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (
            "backend/app/cards/strings.py",
            (
                "# @patient\n"
                'LINES = {"en": ("Call {doctor} today.",), "ms": ("Telefon hari ini.",),'
                ' "zh": ("今天就打电话给{doctor}。",)}\n'
            ),
        ),
    )
    assert _checks(report) == [("slots", "fail")]
    assert "{doctor} missing" in report.findings[0].problem


def test_a_card_said_in_more_lines_in_one_language_is_one_card(tmp_path: Path) -> None:
    """Chinese keeps a date and two numbers apart (rule 10): two lines for one."""
    report = _report(
        tmp_path,
        (
            "backend/app/cards/strings.py",
            (
                "# @patient\n"
                'READING = {"en": ("On {date} it was {top} over {bottom}.",),'
                ' "ms": ("Pada {date} ia {top} atas {bottom}.",),'
                ' "zh": ("{date}您量了血压。", "是{top}比{bottom}。")}\n'
            ),
        ),
    )
    assert report.findings == []


def test_one_english_line_said_two_ways_fails_and_the_glossary_says_which(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (
            "backend/app/cards/strings.py",
            (
                "# @patient\n"
                'CARD = {"en": ("This one we do not wait for.",), "ms": ("Yang ini kita tidak tunggu.",),'
                ' "zh": ("这个我们不等。",)}\n'
            ),
        ),
        (
            "backend/app/replies/strings.py",
            (
                "# @patient\n"
                'REPLY = {"en": ("This one we do not wait for.",), "ms": ("Yang ini kita tidak tunggu.",),'
                ' "zh": ("这个我们不能等。",)}\n'
            ),
        ),
    )
    phrase = [f for f in report.findings if f.check == "phrase"]
    assert [(f.entry_id, f.severity) for f in phrase] == [
        ("backend/app/replies/strings:REPLY.0:zh", "fail")
    ]
    assert phrase[0].fix == 'say "这个我们不等。"'


def test_words_that_change_only_as_a_new_version_are_a_note(tmp_path: Path) -> None:
    """A consent's words are append-only; the finding names the follow-up and does not fail."""
    report = _report(
        tmp_path,
        (
            "backend/app/consent/texts.py",
            (
                "# @patient\n"
                'WORDS = {"en": ("It stays in your record.",), "ms": ("Ia kekal dalam rekod anda.",),'
                ' "zh": ("它留在您的文件里。",)}\n'
            ),
        ),
    )
    assert {(f.check, f.severity) for f in report.findings} == {("never", "note")}
    assert all("new version" in f.fix for f in report.findings)
    assert report.ok


def test_a_word_the_glossary_rules_out_fails_in_any_language(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (
            "backend/app/cards/strings.py",
            (
                "# @patient\n"
                'LETTER = {"en": ("It is in your hospital letter.",),'
                ' "ms": ("Ia dalam surat hospital anda.",), "zh": ("它在您的医院信里。",)}\n'
            ),
        ),
    )
    assert ("never", "fail") in _checks(report)
    assert ("term", "fail") in _checks(report)
    never = next(f for f in report.findings if f.check == "never")
    assert never.fix == 'say "出院信"'


def test_his_word_for_a_thing_is_the_same_phrase_in_malay_and_chinese(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (
            "backend/app/cards/strings.py",
            (
                "# @patient\n"
                'PILL = {"en": ("Take the water pill with breakfast.",),'
                ' "ms": ("Ambil ubat air bersama sarapan.",), "zh": ("早餐时吃去水药。",)}\n'
            ),
        ),
    )
    assert _checks(report) == [("term", "fail")]
    assert report.findings[0].fix == 'say "pil air"'


def test_a_name_said_the_same_in_every_language_is_not_a_translation(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (
            "web/src/strings/en.ts",
            'export const en = {\n  // @patient headline\n  appName: "Nura",\n};\n',
        ),
        (
            "web/src/strings/ms.ts",
            'export const ms = {\n  // @patient headline\n  appName: "Nura",\n};\n',
        ),
        (
            "web/src/strings/zh.ts",
            'export const zh = {\n  // @patient headline\n  appName: "Nura",\n};\n',
        ),
    )
    assert report.findings == []


def test_web_property_paths_and_arrays(tmp_path: Path) -> None:
    source = (
        "export const en = {\n"
        "  refusals: {\n"
        "    // @patient\n"
        '    ConfirmationExpired: ["That yes is too old now.", "Please say yes again."],\n'
        "  },\n"
        "};\n"
    )
    path = _catalogue(tmp_path, "web/src/strings/en.ts", source)
    ids = [e.id for e in memory_module.entries_in(path, tmp_path)]
    assert ids == [
        "web/src/strings:refusals.ConfirmationExpired.0:en",
        "web/src/strings:refusals.ConfirmationExpired.1:en",
    ]


def test_normal_compares_slots_by_their_kind() -> None:
    assert normal("{who} knows now.") == normal("{told} knows now.")
    assert normal("Call {emergency_number} now.") != normal("Call {patient} now.")
    assert normal("{told} 已经知道了。") == normal("{who}已经知道了。")


def test_the_card_a_line_belongs_to() -> None:
    assert parent_of("LINES.flag_family.1") == "LINES.flag_family"
    assert parent_of("MORNING_CARD.line3") == "MORNING_CARD"
    assert parent_of("HEADLINES.flag") == "HEADLINES.flag"


def test_make_language_exits_0_and_says_how_many(capsys: pytest.CaptureFixture[str]) -> None:
    assert memory_module.main(["--quiet-notes"]) == 0
    out = capsys.readouterr().out
    assert "0 failures" in out.splitlines()[-1]

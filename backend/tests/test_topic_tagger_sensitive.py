"""RE-04 acceptance: a sensitive-only text yields no code — and decision D3's opt-in rule
(docs/recommendation-engine.md §3.5) holds: the tagger is never run on search or Ask text
until a caller has checked the (not yet built) `SEARCH_HISTORY` consent, or a preference.

`app.delivery.recommend.topics.TopicTagger`'s own docstring carries the rule; this file is
its one test, in two parts: the tagger's own behaviour (sensitive topics never surface, on
either adapter, whatever else the text also names), and a structural guard that nothing has
wired the tagger into search or Ask ahead of the story that is allowed to (RE-20).
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.delivery.recommend import topics as topics_module
from app.delivery.recommend.topics import FixtureTagger, KeywordTagger, TopicTagger, catalogue

SENSITIVE_ONLY_TEXTS = (
    "am I pregnant",
    "I have been thinking about suicide",
    "could this be HIV",
    "he hit me and I am afraid at home",
)


def test_every_sensitive_topic_is_marked_sensitive() -> None:
    cat = catalogue()
    sensitive = [code for code in cat if cat[code].sensitive]
    assert sensitive, "the catalogue must carry decision D3's sensitive topics"
    for code in sensitive:
        assert cat[code].family == "sensitive"


def test_keyword_tagger_never_returns_a_sensitive_code() -> None:
    tagger = KeywordTagger()
    cat = catalogue()
    for text in SENSITIVE_ONLY_TEXTS:
        assert tagger.tag(text) == (), f"{text!r} must yield no code, sensitive-only"
    # Mixed with an ordinary topic, the ordinary one still surfaces — only the sensitive
    # code itself is withheld, never a topic that stands beside it.
    result = tagger.tag("I am pregnant and my blood pressure is high")
    assert "condition.high_blood_pressure" in result
    assert all(not cat[code].sensitive for code in result)


def test_fixture_tagger_never_returns_a_sensitive_code() -> None:
    tagger = FixtureTagger.load()
    cat = catalogue()
    assert tagger.tag("am I pregnant") == ()
    result = tagger.tag("I'm pregnant and my blood pressure is high")
    assert "condition.high_blood_pressure" in result
    assert all(not cat[code].sensitive for code in result)


def test_the_ports_docstring_states_the_opt_in_rule() -> None:
    doc = (topics_module.__doc__ or "") + (TopicTagger.__doc__ or "")
    assert "D3" in doc
    assert "consent" in doc.lower()
    assert "search" in doc.lower()


SEARCH_MODULES = (
    Path(__file__).resolve().parent.parent / "app" / "search" / "ask.py",
    Path(__file__).resolve().parent.parent / "app" / "delivery" / "feed" / "find.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_topic_tagger_not_wired_to_search() -> None:
    """Decision D3: search-bar and Ask text are not tagged until a consent (or, before it
    exists, a preference) says the profile opted in. Nothing before RE-20 may wire this
    port into either module, so this guard fails the day someone tries."""
    for path in SEARCH_MODULES:
        assert path.is_file(), f"{path} moved; update this guard"
        imports = _imports(path)
        assert not any("recommend.topics" in name for name in imports), (
            f"{path.name} imports the topic tagger; decision D3 says search text is opt-in "
            "only and this module must not run the tagger without checking that first"
        )

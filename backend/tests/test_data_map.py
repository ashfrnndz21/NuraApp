"""The PDPA data map is generated from the models and cannot drift from them (E16-05)."""

from __future__ import annotations

from scripts import data_map


def test_every_column_of_every_table_is_classified() -> None:
    listed = list(data_map.rows())
    assert listed, "no tables on the metadata"
    assert {row[4] for row in listed} <= set(data_map.CLASSIFICATIONS)
    # Nothing test-only reaches the map; every real table does.
    names = {t.name for t in data_map.tables()}
    assert not any(name.startswith("test_") for name in names)
    assert {"person", "profile", "consent", "audit_entry", "fact", "artifact"} <= names


def test_no_classification_is_left_over_for_a_column_that_does_not_exist() -> None:
    """A row in CLASSES for a column the models no longer have is a stale line in the map."""
    present = {f"{t}.{c}" for t, c, *_ in data_map.rows()}
    columns = {c for _, c, *_ in data_map.rows()}
    stale = [
        key
        for key in data_map.CLASSES
        if not (key in present or (key.startswith("*.") and key[2:] in columns))
    ]
    assert stale == []


def test_the_document_carries_the_current_table() -> None:
    assert data_map.check() == []

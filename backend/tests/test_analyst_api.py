"""The Health Analyst over HTTP: `POST /profiles/{id}/insights/stream`, `GET /profiles/{id}/
insights`, `GET /profiles/{id}/insights/{report_id}` (docs/checkpoints.md, the `insight` row
of docs/trust/samd-boundary-review.md)."""

from __future__ import annotations

import json

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591190001"


def _events(text: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.split("\n\n")
        if line.startswith("data: ")
    ]


async def test_no_report_yet_reads_as_a_plain_null_not_a_refusal(deployment: Deployment) -> None:
    """`GET …/insights` is read on every Health screen load, a brand-new profile's first one
    included — "nothing generated yet" is the ordinary case there, not a refusal (package 10's
    #2 defect: a 404 here made the browser log a failed request on every such load)."""
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    got = await deployment.client.get(f"/profiles/{profile_id}/insights", headers=his)
    assert (got.status_code, got.json()) == (200, None)

    empty_list = await deployment.client.get(f"/profiles/{profile_id}/insights/list", headers=his)
    assert (empty_list.status_code, empty_list.json()) == (200, [])

    # An id that genuinely does not exist is still a real 404 — only the "nothing yet" case
    # above changed.
    missing = await deployment.client.get(
        f"/profiles/{profile_id}/insights/00000000-0000-0000-0000-000000000000", headers=his
    )
    assert (missing.status_code, missing.json()) == (404, {"refusal": "NoReportYet"})


async def test_the_stream_yields_steps_in_order_then_a_report_which_get_then_reads_back(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA + "1", "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/insights/stream", json={}, headers=his
    )
    assert streamed.status_code == 200, streamed.text
    events = _events(streamed.text)
    assert [e["type"] for e in events] == ["step", "step", "step", "step", "step", "report"]
    assert [e["key"] for e in events[:-1]] == [
        "records",
        "series",
        "medicines",
        "ledger",
        "coverage",
    ]
    # The bare noun on each step (`STEP_NAME`), the same "What Nura looked at" collapse Ask's
    # own `ASK_STEP_NAMES` already gives — this is what the report screen joins into its one
    # quiet line once the stream settles, never five chips left standing.
    assert [e["name"] for e in events[:-1]] == [
        "what you have told Nura",
        "blood pressure",
        "medicines",
        "what you paid",
        "policies",
    ]
    report = events[-1]["report"]
    assert set(report.keys()) == {
        "report_id",
        "generated_at",
        "week_of",
        "boundary",
        "sections",
        "withheld",
    }
    # His own key generated this report: nothing was withheld from him (docstring,
    # `InsightReportOut.withheld`).
    assert report["withheld"] == []
    assert report["boundary"]
    section_keys = [s["key"] for s in report["sections"]]
    assert section_keys == sorted(
        section_keys,
        key=[
            "what_changed",
            "worth_a_look",
            "medicines_and_supplements",
            "what_you_pay",
            "screenings_due",
            "questions_for_the_doctor",
        ].index,
    )

    latest = await deployment.client.get(f"/profiles/{profile_id}/insights", headers=his)
    assert latest.status_code == 200
    assert latest.json()["report_id"] == report["report_id"]

    by_id = await deployment.client.get(
        f"/profiles/{profile_id}/insights/{report['report_id']}", headers=his
    )
    assert by_id.status_code == 200
    assert by_id.json()["report_id"] == report["report_id"]

    missing = await deployment.client.get(
        f"/profiles/{profile_id}/insights/00000000-0000-0000-0000-000000000000", headers=his
    )
    assert (missing.status_code, missing.json()) == (404, {"refusal": "NoReportYet"})


async def test_insights_list_is_newest_first_summaries_only(deployment: Deployment) -> None:
    """"Health Analyst"'s own past reports (package 10): every report this profile has ever
    had generated, newest first, id/date only — never the sections themselves (those stay
    behind `GET …/insights/{report_id}`)."""
    pa = await register_by_phone(deployment, PA + "2", "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    empty = await deployment.client.get(f"/profiles/{profile_id}/insights/list", headers=his)
    assert (empty.status_code, empty.json()) == (200, [])

    first = await deployment.client.post(
        f"/profiles/{profile_id}/insights/stream", json={}, headers=his
    )
    first_id = _events(first.text)[-1]["report"]["report_id"]
    second = await deployment.client.post(
        f"/profiles/{profile_id}/insights/stream", json={}, headers=his
    )
    second_id = _events(second.text)[-1]["report"]["report_id"]
    assert first_id != second_id

    listed = await deployment.client.get(f"/profiles/{profile_id}/insights/list", headers=his)
    assert listed.status_code == 200
    rows = listed.json()
    assert [row["report_id"] for row in rows] == [second_id, first_id]
    for row in rows:
        assert set(row.keys()) == {"report_id", "generated_at", "week_of"}

    # The literal path `list` is never mistaken for a `report_id`.
    by_id = await deployment.client.get(f"/profiles/{profile_id}/insights/{first_id}", headers=his)
    assert by_id.status_code == 200

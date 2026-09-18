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


async def test_no_report_yet_is_404(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    got = await deployment.client.get(f"/profiles/{profile_id}/insights", headers=his)
    assert (got.status_code, got.json()) == (404, {"refusal": "NoReportYet"})


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

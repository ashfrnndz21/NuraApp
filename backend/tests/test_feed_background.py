"""`app.delivery.feed.background`: the day's self-searches, run off the request (#269/#276,
#280) — walked through the real `GET /feed` route, the way `app.channels.api.feed.feed` and
`app.delivery.feed.background.ensure_learning_scheduled` are actually wired together, not the
module's functions called directly. `tests/conftest.py`'s `_feed_background_isolation`
fixture clears `background._runs` before each test and drains any task still in flight after;
a test that means to see what a run made calls `background.drain()` itself, mid-test, before
reading anything back — the same pattern `tests/test_feed_api.py`'s `_feed_settled` uses.
"""

from __future__ import annotations

import asyncio

import pytest

from app.delivery.feed import background
from app.delivery.feed.models import JobKind
from tests.api import own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_feed_api import _feed, _reading
from tests.test_medicines_api import _add, _artefact, _label

PA = "+6592210001"


async def _medicine(deployment: Deployment, profile_id: str, pa: dict[str, str]) -> None:
    """Amlodipine, thirty tablets: a real gap, so planning queues both an EXPLAINER and a
    SAFETY job (spec §9) — two jobs to a run, not one, for the tests below that care which
    of several jobs failed or ran slowly, and that the others still complete."""
    photo = await _artefact(deployment.client, profile_id, pa)
    added = await _add(
        deployment.client,
        profile_id,
        pa,
        _label("amlodipine", "5 mg", "1 biji sekali sehari pagi", quantity=30),
        photo,
    )
    assert added.status_code == 201, added.text


async def test_jobs_state_moves_from_none_before_any_run_through_looking_to_done(
    deployment: Deployment,
) -> None:
    """`FeedJobsOut.state`: `"none"` before a run has ever been scheduled for the day (no
    record at all, `background.run_state` reads back `None` — the route's own default),
    `"looking"` the moment the first `GET /feed` of the day starts one, `"done"` once it has
    actually finished, however many cards it made."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    assert not background._runs, "nothing has ever asked for this profile's day yet"

    await _reading(deployment, profile_id, pa["token"], 138, 84)
    first = await _feed(deployment, profile_id, pa["token"])
    assert first["jobs"]["state"] == "looking"
    assert first["jobs"]["started_at"] is not None and first["jobs"]["done_at"] is None

    await background.drain()

    second = await _feed(deployment, profile_id, pa["token"])
    assert second["jobs"]["state"] == "done"
    assert second["jobs"]["started_at"] is not None and second["jobs"]["done_at"] is not None


async def test_cards_from_a_finished_run_appear_on_the_next_feed_not_the_one_that_started_it(
    deployment: Deployment,
) -> None:
    """The run's own card is never on the page that started it — it lands in storage the
    moment its job finishes, and shows on the next page load, the same as any other card
    (module docstring)."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _reading(deployment, profile_id, pa["token"], 138, 84)

    first = await _feed(deployment, profile_id, pa["token"])
    assert not [item for item in first["items"] if item["type"] == "learning"], (
        "the run just started; nothing it makes is on this page"
    )

    await background.drain()

    second = await _feed(deployment, profile_id, pa["token"])
    learning = [item for item in second["items"] if item["type"] == "learning"]
    assert learning, "the finished run's card is on the very next page"


async def test_two_concurrent_feed_requests_schedule_one_run_only(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests racing to open the same profile's day claim the run once between them
    (`ensure_learning_scheduled`'s own check-and-set, no `await` in between) — never two runs,
    never a job run twice over."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _reading(deployment, profile_id, pa["token"], 138, 84)

    calls = 0
    real_run_job = background.run_job

    async def _counted(*args: object, **kwargs: object) -> list[object]:
        nonlocal calls
        calls += 1
        return await real_run_job(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(background, "run_job", _counted)

    await asyncio.gather(
        _feed(deployment, profile_id, pa["token"]),
        _feed(deployment, profile_id, pa["token"]),
    )
    await background.drain()

    assert calls == 1, "one run's one job, not scheduled twice by two racing requests"
    settled = await _feed(deployment, profile_id, pa["token"])
    learning = [item for item in settled["items"] if item["type"] == "learning"]
    assert len(learning) == 1, "the job ran once, not once per racing request"


async def test_a_failing_job_does_not_stop_the_others_and_the_run_still_reaches_done(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job that raises is logged and counted as failed; it never stops the others, and the
    run still reaches `"done"` (module docstring)."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _medicine(deployment, profile_id, pa)

    real_run_job = background.run_job

    async def _fail_the_safety_job(*args: object, job: object, **kwargs: object) -> list[object]:
        if getattr(job, "kind", None) is JobKind.SAFETY:
            raise RuntimeError("the safety job's own search blew up")
        return await real_run_job(*args, job=job, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(background, "run_job", _fail_the_safety_job)

    first = await _feed(deployment, profile_id, pa["token"])
    assert first["jobs"]["state"] == "looking"

    await background.drain()

    second = await _feed(deployment, profile_id, pa["token"])
    assert second["jobs"]["state"] == "done", "one job's crash never blocks the run reaching done"
    learning = [item for item in second["items"] if item["type"] == "learning"]
    assert learning, "the explainer job's own card still made it, despite the safety job's crash"


async def test_a_slow_job_hits_its_deadline_is_logged_and_the_others_still_complete(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`JOB_DEADLINE_SECONDS` bounds one job, not the run: a job stuck well past it is timed
    out, logged, and counted as failed — the same as a job that raises — and the run still
    reaches `"done"` with every other job's own cards on it."""
    caplog.set_level("WARNING", logger="nura.delivery.feed")
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _medicine(deployment, profile_id, pa)

    monkeypatch.setattr(background, "JOB_DEADLINE_SECONDS", 0.05)
    real_run_job = background.run_job

    async def _slow_the_safety_job(*args: object, job: object, **kwargs: object) -> list[object]:
        if getattr(job, "kind", None) is JobKind.SAFETY:
            await asyncio.sleep(1)
            return []
        return await real_run_job(*args, job=job, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(background, "run_job", _slow_the_safety_job)

    await _feed(deployment, profile_id, pa["token"])
    await background.drain()

    settled = await _feed(deployment, profile_id, pa["token"])
    assert settled["jobs"]["state"] == "done", "a timed-out job still leaves the run done"
    learning = [item for item in settled["items"] if item["type"] == "learning"]
    assert learning, "the explainer job still completed despite the safety job's timeout"
    assert any(
        "hit its" in record.message and "deadline" in record.message for record in caplog.records
    ), "the timeout itself is logged, the same as any other failed job"

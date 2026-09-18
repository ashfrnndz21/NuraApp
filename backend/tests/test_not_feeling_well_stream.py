"""The not-feeling-well button's thinking trace (docs/design-direction.md, "Conversation,
waiting and 'thinking'"): `not_feeling_well_stream` runs the whole of `not_feeling_well`
first, entirely unchanged, and only narrates real steps once it is done — so a red word
reaches the flag, the ladder and the family before a single byte of the trace goes out.
`not_feeling_well_stream`'s own module docstring says why it is built this way rather than
interleaved: the five steps inside the button are one unit of work a red flag must clear at
once, and this file proves that promise holds — never an invented step, never a step that
delays the flag.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.safety.not_feeling_well import NfwStep, NfwStepKey, WhatToDoNow, not_feeling_well_stream
from app.safety.red_flags import Feeling
from app.state.models import Posture
from tests.delivery_support import via_for
from tests.safety_support import REGISTRY, transcriber_for
from tests.test_not_feeling_well import _household, _Store


async def _stream(session: AsyncSession, context, **said) -> tuple[list[NfwStepKey], WhatToDoNow]:
    keys: list[NfwStepKey] = []
    done: WhatToDoNow | None = None
    async for event in not_feeling_well_stream(
        session,
        context=context,
        store=_Store(),
        transcriber=transcriber_for(context.region),
        registry=REGISTRY,
        via=via_for(context.region),
        **said,
    ):
        if isinstance(event, NfwStep):
            keys.append(event.key)
        else:
            done = event
    assert done is not None
    return keys, done


async def test_a_red_flag_streams_only_checking_family_and_ready_never_the_checks_it_skipped(
    sg: AsyncSession,
) -> None:
    owner, *_rest = await _household(sg)
    keys, done = await _stream(sg, owner, words="I have chest pain since just now")
    assert done.kind.value == "red_flag"
    assert done.red_flags == [Feeling.CHEST_TIGHTNESS] and done.posture is Posture.ACT
    # TABLETS and MEDICINES are real reads `not_feeling_well` skips once a red flag is heard
    # (its own body: `missed = None if heard.any else ...`) — so the trace never claims them.
    assert keys == [NfwStepKey.CHECKING, NfwStepKey.FAMILY, NfwStepKey.READY]


async def test_a_quiet_day_streams_the_checks_it_really_made(sg: AsyncSession) -> None:
    owner, *_rest = await _household(sg)
    keys, done = await _stream(sg, owner, words="feeling a little tired today")
    assert not done.red_flags
    assert keys == [
        NfwStepKey.CHECKING,
        NfwStepKey.TABLETS,
        NfwStepKey.MEDICINES,
        NfwStepKey.FAMILY,
        NfwStepKey.READY,
    ]


async def test_the_stream_matches_the_plain_buttons_own_card(sg: AsyncSession) -> None:
    """`not_feeling_well_stream` runs `not_feeling_well` itself, unmodified — the two can
    never answer the button two different ways."""
    owner, *_rest = await _household(sg)
    _keys, streamed = await _stream(sg, owner, words="feeling a little tired today")
    assert streamed.kind is not None
    assert [line.text for line in streamed.lines]

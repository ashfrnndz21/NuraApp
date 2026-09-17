"""Pa's and Mei's own numbers on a seeded demo/dev deployment (`app.demo_seed`), one pair per
region, in the reserved test range (`app.demo.is_demo_number`): distinctive and fixed, so
`app.demo_seed` (who it seeds) and `app.channels.api.demo_signin` (who "Try it as Pa"/"Try it
as Mei" signs in as) agree on the two numbers without either reaching into the other — this
is its own module, with no service imports, only so that agreement never becomes a cycle.
"""

from __future__ import annotations

from app.regions import Region

DEMO_NUMBERS: dict[Region, tuple[str, str]] = {
    Region.SG: ("+6500001111", "+6500002222"),
    Region.MY: ("+60000011111", "+60000022222"),
}


def pa_number(region: Region) -> str:
    return DEMO_NUMBERS[region][0]


def mei_number(region: Region) -> str:
    return DEMO_NUMBERS[region][1]

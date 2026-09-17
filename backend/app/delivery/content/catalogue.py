"""Which item is which: the structural half of the fixture set (`app.delivery.content.strings`
holds the words). Not patient strings itself — `category`, `slug` and `meta`'s keys and
values are vocabulary, not sentences — so nothing here is tagged `# @patient`.

`meta` holds only structured, non-identifying detail a screen needs: a format, a duration, a
day of the week, a kind of contact. Nothing here is a specific named organisation, a phone
number or an address — those are left for a real deployment's live source (external
dependency, docs/design-direction.md's feature table) rather than invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.delivery.feed.models import CardType
from app.regions import Region


@dataclass(frozen=True, slots=True)
class ItemSpec:
    """One row to seed: `key` looks up its title and summary in `strings.py`; `body_key`
    looks up its body lines there too (a second key when the region's own body differs, the
    way `activity_chair_exercise_my`'s class meets on a different morning)."""

    key: str
    content_type: CardType
    region: Region
    slug: str
    category: str
    body_key: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved_body_key(self) -> str:
        return self.body_key or self.key


ITEMS: tuple[ItemSpec, ...] = (
    # --- Activities: "Stay engaged" ---------------------------------------------------------
    ItemSpec(
        key="activity_chair_exercise",
        content_type=CardType.ACTIVITY,
        region=Region.SG,
        slug="activity-chair-exercise",
        category="movement",
        meta={"format": "class", "duration_minutes": 45},
    ),
    ItemSpec(
        key="activity_chair_exercise",
        body_key="activity_chair_exercise_my",
        content_type=CardType.ACTIVITY,
        region=Region.MY,
        slug="activity-chair-exercise",
        category="movement",
        meta={"format": "class", "duration_minutes": 45},
    ),
    ItemSpec(
        key="activity_tai_chi",
        content_type=CardType.ACTIVITY,
        region=Region.SG,
        slug="activity-tai-chi",
        category="movement",
        meta={"format": "class", "duration_minutes": 30},
    ),
    ItemSpec(
        key="activity_tea_chat",
        content_type=CardType.ACTIVITY,
        region=Region.MY,
        slug="activity-tea-chat",
        category="social",
        meta={"format": "gathering", "duration_minutes": 60},
    ),
    # --- Care Services: "Professional help" -------------------------------------------------
    ItemSpec(
        key="service_home_nursing",
        content_type=CardType.CARE_SERVICE,
        region=Region.SG,
        slug="service-home-nursing",
        category="home_nursing",
        meta={"contact_kind": "call_to_book"},
    ),
    ItemSpec(
        key="service_physio",
        content_type=CardType.CARE_SERVICE,
        region=Region.SG,
        slug="service-physio",
        category="physiotherapy",
        meta={"contact_kind": "call_to_book"},
    ),
    ItemSpec(
        key="service_meal_delivery",
        content_type=CardType.CARE_SERVICE,
        region=Region.MY,
        slug="service-meal-delivery",
        category="meal_delivery",
        meta={"contact_kind": "call_to_book"},
    ),
    ItemSpec(
        key="service_transport",
        content_type=CardType.CARE_SERVICE,
        region=Region.MY,
        slug="service-transport",
        category="transport",
        meta={"contact_kind": "call_to_book"},
    ),
    # --- Resources: "Guides & support" ------------------------------------------------------
    ItemSpec(
        key="resource_falls",
        content_type=CardType.RESOURCE,
        region=Region.SG,
        slug="resource-falls",
        category="home_safety",
        meta={"read_time_minutes": 2},
    ),
    ItemSpec(
        key="resource_doctor_visit",
        content_type=CardType.RESOURCE,
        region=Region.SG,
        slug="resource-doctor-visit",
        category="talking_to_doctor",
        meta={"read_time_minutes": 1},
    ),
    ItemSpec(
        key="resource_falls",
        content_type=CardType.RESOURCE,
        region=Region.MY,
        slug="resource-falls",
        category="home_safety",
        meta={"read_time_minutes": 2},
    ),
    ItemSpec(
        key="resource_heat",
        content_type=CardType.RESOURCE,
        region=Region.MY,
        slug="resource-heat",
        category="home_safety",
        meta={"read_time_minutes": 1},
    ),
    # --- Community: Local Events -------------------------------------------------------------
    ItemSpec(
        key="event_market",
        body_key="event_market_sg",
        content_type=CardType.LOCAL_EVENT,
        region=Region.SG,
        slug="event-market",
        category="market",
        meta={"when": "Saturday mornings"},
    ),
    ItemSpec(
        key="event_market",
        body_key="event_market_my",
        content_type=CardType.LOCAL_EVENT,
        region=Region.MY,
        slug="event-market",
        category="market",
        meta={"when": "Sunday mornings"},
    ),
    # --- Community: Volunteer -----------------------------------------------------------------
    ItemSpec(
        key="volunteer_reading",
        content_type=CardType.VOLUNTEER,
        region=Region.SG,
        slug="volunteer-reading",
        category="children",
        meta={"commitment": "one hour a week"},
    ),
    ItemSpec(
        key="volunteer_meals",
        content_type=CardType.VOLUNTEER,
        region=Region.MY,
        slug="volunteer-meals",
        category="meal_delivery",
        meta={"commitment": "one hour a week"},
    ),
    # --- Community: Support Groups -------------------------------------------------------------
    ItemSpec(
        key="support_caregivers",
        body_key="support_group",
        content_type=CardType.SUPPORT_GROUP,
        region=Region.SG,
        slug="support-caregivers",
        category="caregiving",
        meta={"cadence": "monthly"},
    ),
    ItemSpec(
        key="support_stroke",
        body_key="support_group",
        content_type=CardType.SUPPORT_GROUP,
        region=Region.MY,
        slug="support-stroke",
        category="stroke",
        meta={"cadence": "monthly"},
    ),
)

"""His policies: what he is insured under, typed on a yes.

    Insurer, policy reference, type, who is covered, start and renewal dates, status,
    what it covers in his own words, and when the premium is due.

E13-01 built one field for the emergency card — the insurer's name and a policy reference.
This is the fuller record: every policy on the profile, hospital or integrated shield,
outpatient, critical illness, or a government scheme (MediShield Life, MySalam), each with
who it covers, when it started, when it renews, when the premium falls due, and what it
covers as he or his chief put it in words — typed directly, or copied in after reading a
policy document through the one upload and review-card path the record already has
(`app.ingestion.review`): that path always writes Facts, never a policy row directly, so the
words a chief read off a letter still pass through her own yes here, the same as a policy
she never saw a letter for.

**The scope decision, written down.** A policy is read and written under `Scope.MONEY`, the
door already reserved for "your insurance letters" (`app.consent.texts.SCOPE_WORDS`) and
already preset to nobody but a chief (`app.keys.scopes.ROLE_SCOPES`) — the owner always
holds it, a steward holds it before a claim, a chief a family names for it holds it, and a
helper, a viewer, an emergency-only key or a clinic key do not. That is deliberate: what a
policy pays for and what it costs is money, not what a stranger needs to save him in an
emergency (`Scope.EMERGENCY`, which every role holds, is what `app.insurance.insurer` keeps
using for the one line the emergency card says). No new scope is added here, and no role's
preset changes; a policy is simply one more thing MONEY already meant.

**A change is a new row.** Like the insurer, a policy is never edited: a correction —
another renewal date, a lapsed status — writes a new row naming the one it replaces
(`supersedes_id`), and the row it replaces is marked `superseded_at`, the one change a
written policy takes. `current_policies` reads the newest of each lineage, tied on
`(set_at, id)` so two rows written in the same instant still resolve to one winner. A
profile holds more than one policy at once — the government scheme and a private hospital
plan, say — so, unlike the single insurer on the card, this is a set, one lineage per
`supersedes_id` chain.

No identifier crosses this module: `policy_reference` never appears in a log line, an audit
line (`app.audit.access` never writes column values, only which table and how many rows),
a card, or a message. `looks_like_an_identity_card` (`app.insurance.insurer`) refuses one
written into `policy_reference` however it is written, the same guard the insurer already
uses; an identity-card number is not a policy reference, and this module keeps one only
where a guarantee letter needs it, which no path here does yet.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, utcnow
from app.drafts import PolicyDraft
from app.errors import Refusal
from app.insurance.insurer import looks_like_an_identity_card
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.models import _row_of_profile, _tied_to_profile
from app.regions import REGION_TZ

POLICY_SCOPE = Scope.MONEY
TARGET = "policy"

INSURER_NAME_LENGTH = 120
REFERENCE_LENGTH = 40
COVERED_LENGTH = 120
COVERS_LENGTH = 400
WAITING_PERIOD_LENGTH = 200
CLAIMS_CONTACT_LENGTH = 200
PLAN_LENGTH = 120

ESSENTIAL_ITEM_TEXT_LENGTH = 200
"""The same cap the extractor's own field value already carries
(`app.ingestion.extract.VALUE_LENGTH`) — an essentials line is one extracted field, never
longer once it is his record either."""
ESSENTIAL_LIST_CAP = 12
"""How many lines a covers/excludes/benefits/how-to-claim section may hold — the same ceiling
the extraction prompt is given (`app/llm/prompts/extract_document.txt`), enforced again here
so a hostile or runaway answer can never write more than a policy's own pages plausibly
carry. Left at 12 for every list, `excludes` included: raising it would need a second model
call to stay inside the one extraction call's own output-token budget
(`app.llm.claude_extract.MAX_TOKENS`), and this package does not raise spend (independent
review, package 12a fix round, item 4) — so a longer schedule is read only as far as the
first 12 lines, and told so (`ESSENTIALS_CUT_NAMES`, below)."""

ESSENTIALS_CUT_NAMES: tuple[str, ...] = ("coverage_items", "excludes", "benefits", "claim_steps")
"""The four essentials lists, in the order `PolicyOut.essentials_cut` names one of them in:
whichever of these a write actually truncated at `ESSENTIAL_LIST_CAP` (`_clean_essentials`),
never inferred by a caller from a list's length being exactly 12 (independent review, item
4) — that reads as "a policy that happens to print exactly a dozen lines" the same as one
that printed forty, so the cut is recorded here, at the one place the truncation happens, and
carried on the row itself."""

FAR_FUTURE_DAYS = 50 * 365
"""A policy's own end or renewal date is refused past this (`policy_draft`, independent
review item 1): fifty years is generously past any real renewal cycle, so a date this far out
is a misread digit, not a fact — refused the same way a renewal before the start date already
is, rather than quietly written and shown as if it were real."""


@dataclass(frozen=True, slots=True)
class EssentialItem:
    """One line of what a policy covers, does not cover, a benefit, or a step to claim —
    exactly as printed, with the page it came from. Extractor-written text: shown to him as a
    plain string only, never markup, never a link (`web/src/insurance/model.ts`
    `sanitizeDisplayText`); this module keeps it as text too, never parses an amount out of a
    `benefit` line into a number Nura could compute with."""

    text: str
    page: int | None = None

    def as_json(self) -> dict[str, Any]:
        return {"text": self.text, "page": self.page}

    @staticmethod
    def from_json(raw: Any) -> EssentialItem | None:
        if not isinstance(raw, dict):
            return None
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        page = raw.get("page")
        return EssentialItem(text=text, page=page if isinstance(page, int) else None)


class PolicyType(StrEnum):
    """What kind of cover this is, in the words the family uses for it."""

    HOSPITAL = "hospital"
    """Hospital or integrated shield: what pays the hospital bill."""
    OUTPATIENT = "outpatient"
    CRITICAL_ILLNESS = "critical_illness"
    GOVERNMENT_SCHEME = "government_scheme"
    """MediShield Life in Singapore, MySalam in Malaysia: the national scheme, not a private
    policy, but on the same list because it is still cover he holds."""


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    LAPSED = "lapsed"
    CANCELLED = "cancelled"


class PolicyPeriodState(StrEnum):
    """The passport's own quiet state chip: never inferred on the client from a free-text
    field, always this one pure function, fed the profile's own wall-clock day
    (`app.regions.REGION_TZ`, the same clock `app.insurance.ledger._this_year` already reads
    off `app.clock.utcnow`) — so a frozen-clock test and a real deployment agree.

    Independent review (package 12a fix round, item 1) found the first pass claiming a
    validity Nura cannot actually know: a paper-loaded policy always wrote `renewal_date` as
    `None` (`ProposePolicy.tsx` puts the printed end date in `ends_on`, which this state never
    read), so every one of them showed `IN_FORCE` forever, a green chip beside a date years in
    the past. Nura only ever knows what the paper says and what he last typed — never whether
    a premium was actually paid — so the words now say only that: the date the paper prints,
    or that the dates on file have passed, never that cover "is in force."""

    RUNS_TO = "runs_to"
    """Active, with an end date on file (`policy_period_date`) that has not yet passed — said
    with that date, never that cover is currently valid."""
    ENDED = "ended"
    """Lapsed or cancelled by a person's own word, or the end date on file has already
    passed — a policy this old is never shown as current."""
    UNDATED = "undated"
    """Active, with no end date and no renewal date on file at all: nothing to show a chip
    about, so none is shown, rather than a chip claiming a validity nothing on file supports."""


def policy_period_date(*, renewal_date: date | None, ends_on: date | None) -> date | None:
    """The one end date the chip and the passport's own period line both read: the policy's
    own printed end date (`ends_on`) when there is one, `renewal_date` otherwise. Independent
    review note 9: before this, the chip read `renewal_date` and the card read `ends_on`
    separately, so the same policy could show two different dates — every caller reads the
    date through this one function now, never the two columns apart."""
    return ends_on if ends_on is not None else renewal_date


def policy_period_state(
    *, status: PolicyStatus, renewal_date: date | None, ends_on: date | None, today: date
) -> PolicyPeriodState:
    """The chip, from what is actually on file: `status` is the person's own word and always
    wins when it says the cover has lapsed or was cancelled. Otherwise the end date on file
    (`policy_period_date` — `ends_on` first, then `renewal_date`) decides: already behind
    `today` is ended, still ahead is said with that date, and no date on file at all draws no
    chip rather than one claiming cover it cannot know is current."""
    if status is not PolicyStatus.ACTIVE:
        return PolicyPeriodState.ENDED
    effective = policy_period_date(renewal_date=renewal_date, ends_on=ends_on)
    if effective is None:
        return PolicyPeriodState.UNDATED
    if effective < today:
        return PolicyPeriodState.ENDED
    return PolicyPeriodState.RUNS_TO


class Policy(ProfileScoped, Base):
    """One policy, as typed on a yes. A correction is a new row; the newest of each lineage
    is in force (`current_policies`)."""

    __tablename__ = TARGET
    __table_args__ = (
        _row_of_profile(TARGET),
        _tied_to_profile(TARGET, "supersedes_id", TARGET),
        _tied_to_profile(TARGET, "review_card_id", "review_card"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    insurer_name: Mapped[str] = mapped_column(String(INSURER_NAME_LENGTH))
    policy_reference: Mapped[str | None] = mapped_column(String(REFERENCE_LENGTH), default=None)
    policy_type: Mapped[PolicyType] = mapped_column(enum_column(PolicyType, "policy_type"))
    covered: Mapped[str | None] = mapped_column(String(COVERED_LENGTH), default=None)
    """Who the policy covers, in words the family already uses for them ("Pa and Mum"), not
    a list of profiles: a policy often covers someone who has no profile of his own here."""
    covers: Mapped[str | None] = mapped_column(String(COVERS_LENGTH), default=None)
    """What it covers, as he or his chief put it in words — "hospital stays, up to $500 a
    day" — never a coverage Nura decided (`app.insurance.relevance`)."""
    start_date: Mapped[date | None] = mapped_column(Date(), default=None)
    renewal_date: Mapped[date | None] = mapped_column(Date(), default=None)
    premium_due_date: Mapped[date | None] = mapped_column(Date(), default=None)
    """When the premium is next due, so a reminder can be raised before cover lapses — raised
    by the delivery engine's own triggers (`app.delivery.triggers`), which is not this
    module's job; this column is what it would read."""
    status: Mapped[PolicyStatus] = mapped_column(enum_column(PolicyStatus, "policy_status"))
    guarantee_letter: Mapped[bool] = mapped_column(Boolean, default=False)
    """Whether this insurer works by guarantee letter at the hospital desk, as the chief has
    been told — not something Nura looks up (`app.insurance.relevance`)."""
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{TARGET}.id"), default=None)
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)
    set_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    confirmation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("confirmation.id"))
    set_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    plan: Mapped[str | None] = mapped_column(String(PLAN_LENGTH), default=None)
    """The plan's own name, exactly as printed ("Hospital Shield") — its own column, never
    folded into `covers` (what it covers, in words), the mistake the passport's first pass
    made."""

    # The essentials (package 12a): what a policy document itself prints, each line its own
    # extracted field before it ever reaches here, kept as a JSON list of `EssentialItem`
    # (`{"text", "page"}`) — never a number Nura parses out and computes with, never longer
    # than `ESSENTIAL_LIST_CAP` items of `ESSENTIAL_ITEM_TEXT_LENGTH` characters each
    # (`policy_draft`, below, is the one door these ever pass through, the same as every other
    # field here).
    coverage_items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), default=None)
    """What the policy's own pages say it covers, one line per printed item."""
    excludes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), default=None)
    """What the policy's own pages say it does not cover, one line per printed item."""
    benefits: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), default=None)
    """A benefit or a limit, the item's own words together with its amount exactly as
    printed, including its currency — kept as one text line, never split into a number this
    module or anything downstream could compute with."""
    claim_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), default=None)
    """How to claim, in the policy's own order — the list order is the claim order; no
    separate index is kept."""
    ends_on: Mapped[date | None] = mapped_column(Date(), default=None)
    """The policy's own fixed end date, when its pages print one (distinct from
    `renewal_date`, which is when it next comes up for renewal, not necessarily printed)."""
    waiting_period: Mapped[str | None] = mapped_column(String(WAITING_PERIOD_LENGTH), default=None)
    """A waiting period before cover starts for a condition, exactly as printed."""
    claims_contact: Mapped[str | None] = mapped_column(String(CLAIMS_CONTACT_LENGTH), default=None)
    """A phone number, hotline or claims-department name exactly as printed — display-only
    text everywhere it is shown (`web/src/insurance/model.ts` `sanitizeDisplayText`): never
    turned into a `tel:`/`http` link, since nothing here has reviewed it the way
    `app.insurance.insurer`'s catalogue-style data would be."""
    review_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("review_card.id"), default=None
    )
    """The confirmed review card this policy's essentials were read from, when it was loaded
    from a paper rather than typed — "See the policy itself" reads the same audited artifact
    route a reopened paper already uses (`GET .../review-cards/{card_id}/artifact`), under
    that route's own `Scope.RECORDS` gate, not a new one. Tied to the profile with it
    (`_tied_to_profile`, `__table_args__`), the same discipline every other cross-table
    reference on this row already keeps (`supersedes_id`) — a bare single-column
    `ForeignKey("review_card.id")` would let a row point at another profile's card entirely,
    which the plain `id` alone cannot refuse (independent review, item 7)."""
    essentials_cut: Mapped[list[str] | None] = mapped_column(JSON(), default=None)
    """Which of `coverage_items`/`excludes`/`benefits`/`claim_steps` (`ESSENTIALS_CUT_NAMES`)
    this write actually truncated at `ESSENTIAL_LIST_CAP` — `None`/empty when none was,
    `NULL` never standing in for "nothing was cut" versus "nothing was asked" the way an
    empty list already does for the essentials themselves. Set only by `_clean_essentials`,
    from the list it was actually given, never inferred by a caller from a list's length
    happening to equal the cap (independent review, item 4)."""


# Supersession is the one change a written policy takes.
frozen(Policy, except_for=frozenset({"superseded_at"}))


class NotTheirsToSetAPolicy(Refusal):
    """A policy is typed by him, the steward holding his graph, or the chief he named — the
    same hands the insurer on the card already trusts (`app.insurance.insurer`)."""


class NotAPolicy(Refusal):
    """An insurer's name is 1 to 120 characters; a policy reference, up to 40; what it covers
    and who it covers, short lines; a renewal before a start date is not a policy."""


class NotAPolicyReference(Refusal):
    """An identity-card number is not a policy reference, and is not kept here."""


class NoSuchPolicy(Refusal):
    """No policy by that id on this profile."""


def may_set_a_policy(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role is KeyRole.CHIEF:
        return
    raise NotTheirsToSetAPolicy(f"a {context.role} key reads policies; it does not set them")


_CONTROL_CHARS_RE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f-\\x9f]")
_BIDI_CONTROL_RE = re.compile("[\\u00ad\\u061c\\u200b-\\u200f\\u202a-\\u202e\\u2066-\\u2069\\ufeff]")
"""The same code-point ranges `web/src/insurance/model.ts` `sanitizeDisplayText` strips for
display, plus the zero-width/joiner and BOM code points the independent review's probe named
by example (U+200B survives a plain bidi-override strip) — stripped here too, at write
(package 12a fix round, item 6), so a hostile control or bidi-override character never
reaches storage at all rather than relying on every future reader to strip it again.
`CONTROL_CHARS_RE` leaves `\\t`/`\\n`/`\\r` alone; `text.split()` below already collapses
those to a single space."""


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = _BIDI_CONTROL_RE.sub("", _CONTROL_CHARS_RE.sub("", text))
    one_line = " ".join(stripped.split())
    return one_line or None


def _not_an_identity_card(*values: str | None) -> None:
    if any(one is not None and looks_like_an_identity_card(one) for one in values):
        raise NotAPolicyReference("that holds an identity-card number")


def _clean_essentials(
    items: Sequence[EssentialItem] | None,
) -> tuple[tuple[dict[str, Any], ...], bool]:
    """A covers/excludes/benefits/claim_steps list, capped and cleaned — never more than
    `ESSENTIAL_LIST_CAP` items, never an item over `ESSENTIAL_ITEM_TEXT_LENGTH` characters, a
    blank line dropped rather than kept as an empty one. Stored as plain JSON-ready dicts
    (`EssentialItem.as_json`); order is the list's own order, the claim order or the printed
    order, kept exactly as given.

    Returns the cleaned list and whether it was actually cut: `len(items) > ESSENTIAL_LIST_CAP`
    before cleaning, the one place this is decided (independent review, item 4) — a caller
    never infers a cut from the cleaned list's own length happening to equal the cap, since a
    policy that prints exactly twelve lines is indistinguishable from one that prints forty
    unless the truncation is recorded here, where it happens."""
    if not items:
        return (), False
    cut = len(items) > ESSENTIAL_LIST_CAP
    cleaned: list[dict[str, Any]] = []
    for item in items[:ESSENTIAL_LIST_CAP]:
        text = _clean(item.text)
        if text is None:
            continue
        if len(text) > ESSENTIAL_ITEM_TEXT_LENGTH:
            raise NotAPolicy(f"a policy essential line is at most {ESSENTIAL_ITEM_TEXT_LENGTH} characters")
        _not_an_identity_card(text)
        cleaned.append(EssentialItem(text=text, page=item.page).as_json())
    return tuple(cleaned), cut


def _not_far_future(label: str, value: date | None, today: date) -> None:
    if value is not None and (value - today).days > FAR_FUTURE_DAYS:
        raise NotAPolicy(f"a {label} is not more than {FAR_FUTURE_DAYS // 365} years away")


def policy_draft(
    *,
    insurer_name: str,
    policy_reference: str | None,
    policy_type: PolicyType,
    covered: str | None,
    covers: str | None,
    start_date: date | None,
    renewal_date: date | None,
    premium_due_date: date | None,
    status: PolicyStatus,
    guarantee_letter: bool,
    supersedes_id: uuid.UUID | None,
    plan: str | None = None,
    coverage_items: Sequence[EssentialItem] | None = None,
    excludes: Sequence[EssentialItem] | None = None,
    benefits: Sequence[EssentialItem] | None = None,
    claim_steps: Sequence[EssentialItem] | None = None,
    ends_on: date | None = None,
    waiting_period: str | None = None,
    claims_contact: str | None = None,
    review_card_id: uuid.UUID | None = None,
    today: date | None = None,
) -> PolicyDraft:
    """A policy as it will be kept, or a refusal naming what is wrong with it. `today` is the
    day a far-future date is refused against (`FAR_FUTURE_DAYS`) — the app's own frozen clock
    (`app.db.utcnow`) when a caller has no region-aware day of its own to give."""
    effective_today = today if today is not None else utcnow().date()
    named = _clean(insurer_name)
    reference = _clean(policy_reference)
    who = _clean(covered)
    what = _clean(covers)
    plan_named = _clean(plan)
    waiting = _clean(waiting_period)
    contact = _clean(claims_contact)
    if named is None:
        raise NotAPolicy("a policy names an insurer")
    if len(named) > INSURER_NAME_LENGTH:
        raise NotAPolicy(f"an insurer's name is at most {INSURER_NAME_LENGTH} characters")
    if reference is not None and len(reference) > REFERENCE_LENGTH:
        raise NotAPolicy(f"a policy reference is at most {REFERENCE_LENGTH} characters")
    if who is not None and len(who) > COVERED_LENGTH:
        raise NotAPolicy(f"who is covered is at most {COVERED_LENGTH} characters")
    if what is not None and len(what) > COVERS_LENGTH:
        raise NotAPolicy(f"what it covers is at most {COVERS_LENGTH} characters")
    if plan_named is not None and len(plan_named) > PLAN_LENGTH:
        raise NotAPolicy(f"a plan name is at most {PLAN_LENGTH} characters")
    if waiting is not None and len(waiting) > WAITING_PERIOD_LENGTH:
        raise NotAPolicy(f"a waiting period is at most {WAITING_PERIOD_LENGTH} characters")
    if contact is not None and len(contact) > CLAIMS_CONTACT_LENGTH:
        raise NotAPolicy(f"a claims contact is at most {CLAIMS_CONTACT_LENGTH} characters")
    if start_date is not None and renewal_date is not None and renewal_date < start_date:
        raise NotAPolicy("a renewal date is not before the start date")
    if start_date is not None and ends_on is not None and ends_on < start_date:
        raise NotAPolicy("an end date is not before the start date")
    _not_far_future("renewal date", renewal_date, effective_today)
    _not_far_future("end date", ends_on, effective_today)
    _not_an_identity_card(named, reference, who, what, plan_named, waiting, contact)
    coverage_items_clean, coverage_items_cut = _clean_essentials(coverage_items)
    excludes_clean, excludes_cut = _clean_essentials(excludes)
    benefits_clean, benefits_cut = _clean_essentials(benefits)
    claim_steps_clean, claim_steps_cut = _clean_essentials(claim_steps)
    essentials_cut = tuple(
        name
        for name, cut in zip(
            ESSENTIALS_CUT_NAMES,
            (coverage_items_cut, excludes_cut, benefits_cut, claim_steps_cut),
            strict=True,
        )
        if cut
    )
    return PolicyDraft(
        insurer_name=named,
        policy_reference=reference,
        policy_type=policy_type,
        covered=who,
        covers=what,
        start_date=start_date,
        renewal_date=renewal_date,
        premium_due_date=premium_due_date,
        status=status,
        guarantee_letter=guarantee_letter,
        supersedes_id=supersedes_id,
        plan=plan_named,
        coverage_items=coverage_items_clean,
        excludes=excludes_clean,
        benefits=benefits_clean,
        claim_steps=claim_steps_clean,
        ends_on=ends_on,
        waiting_period=waiting,
        claims_contact=contact,
        review_card_id=review_card_id,
        essentials_cut=essentials_cut,
    )


@audited(Action.READ, POLICY_SCOPE, TARGET)
async def current_policies(session: AsyncSession, *, context: KeyContext) -> list[Policy]:
    """Every policy in force: the newest row of each lineage that is not itself superseded,
    tied on `(set_at, id)` so a tie never picks an arbitrary one."""
    rows = await audited_read(session, Policy, context, POLICY_SCOPE)
    newest_by_lineage: dict[uuid.UUID, Policy] = {}
    for row in rows:
        if row.superseded_at is not None:
            continue
        lineage = _lineage_head(rows, row)
        current = newest_by_lineage.get(lineage)
        if current is None or (as_utc(row.set_at), str(row.id)) > (
            as_utc(current.set_at),
            str(current.id),
        ):
            newest_by_lineage[lineage] = row
    return sorted(
        newest_by_lineage.values(), key=lambda row: (as_utc(row.set_at), str(row.id)), reverse=True
    )


def _lineage_head(rows: Sequence[Policy], row: Policy) -> uuid.UUID:
    """The id a lineage is filed under: the first row that started it, walking `supersedes_id`
    back through the rows already read. A row whose ancestor was not read (another scope, a
    different page) is its own lineage — it is still exactly one policy to the reader."""
    by_id = {one.id: one for one in rows}
    seen: set[uuid.UUID] = set()
    current = row
    while current.supersedes_id is not None and current.supersedes_id in by_id:
        if current.id in seen:
            break  # a cycle cannot happen through this module's own writes; refuse to loop
        seen.add(current.id)
        current = by_id[current.supersedes_id]
    return current.id


@audited(Action.WRITE, POLICY_SCOPE, TARGET)
async def set_a_policy(
    session: AsyncSession,
    *,
    context: KeyContext,
    insurer_name: str,
    policy_reference: str | None,
    policy_type: PolicyType,
    covered: str | None,
    covers: str | None,
    start_date: date | None,
    renewal_date: date | None,
    premium_due_date: date | None,
    status: PolicyStatus,
    guarantee_letter: bool,
    supersedes_id: uuid.UUID | None,
    confirmation_id: uuid.UUID,
    plan: str | None = None,
    coverage_items: Sequence[EssentialItem] | None = None,
    excludes: Sequence[EssentialItem] | None = None,
    benefits: Sequence[EssentialItem] | None = None,
    claim_steps: Sequence[EssentialItem] | None = None,
    ends_on: date | None = None,
    waiting_period: str | None = None,
    claims_contact: str | None = None,
    review_card_id: uuid.UUID | None = None,
) -> Policy:
    """Write a policy down — new, or a correction of one already held — on the typer's own
    yes for exactly these words.

    The draft is rebuilt here from the fields about to be written, never taken as given: the
    yes must match what this call is about to do, not what a caller says it once matched
    (the same rule `app.insurance.insurer.set_insurer` already keeps).
    """
    may_set_a_policy(context)
    draft = policy_draft(
        insurer_name=insurer_name,
        policy_reference=policy_reference,
        policy_type=policy_type,
        covered=covered,
        covers=covers,
        start_date=start_date,
        renewal_date=renewal_date,
        premium_due_date=premium_due_date,
        status=status,
        guarantee_letter=guarantee_letter,
        supersedes_id=supersedes_id,
        plan=plan,
        coverage_items=coverage_items,
        excludes=excludes,
        benefits=benefits,
        claim_steps=claim_steps,
        ends_on=ends_on,
        waiting_period=waiting_period,
        claims_contact=claims_contact,
        review_card_id=review_card_id,
        today=utcnow().astimezone(REGION_TZ[context.region]).date(),
    )
    if draft.supersedes_id is not None:
        found = await audited_read(
            session, Policy, context, POLICY_SCOPE, where=(Policy.id == draft.supersedes_id,)
        )
        if not found:
            raise NoSuchPolicy(f"no policy {draft.supersedes_id} on profile {context.profile_id}")
        old = found[0]
        if old.superseded_at is not None:
            raise NoSuchPolicy(f"policy {draft.supersedes_id} was already replaced")
    else:
        old = None
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    moment = utcnow()
    written = await audited_write(
        session,
        Policy,
        context,
        POLICY_SCOPE,
        insurer_name=draft.insurer_name,
        policy_reference=draft.policy_reference,
        policy_type=draft.policy_type,
        covered=draft.covered,
        covers=draft.covers,
        start_date=draft.start_date,
        renewal_date=draft.renewal_date,
        premium_due_date=draft.premium_due_date,
        status=draft.status,
        guarantee_letter=draft.guarantee_letter,
        supersedes_id=draft.supersedes_id,
        plan=draft.plan,
        coverage_items=list(draft.coverage_items) or None,
        excludes=list(draft.excludes) or None,
        benefits=list(draft.benefits) or None,
        claim_steps=list(draft.claim_steps) or None,
        ends_on=draft.ends_on,
        waiting_period=draft.waiting_period,
        claims_contact=draft.claims_contact,
        review_card_id=draft.review_card_id,
        essentials_cut=list(draft.essentials_cut) or None,
        set_by_person_id=yes.person_id,
        confirmation_id=yes.id,
        set_at=moment,
    )
    if old is not None:
        old.superseded_at = moment
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=POLICY_SCOPE,
            target=TARGET,
            target_id=old.id,
            rows=1,
        )
    return written


__all__ = [
    "CLAIMS_CONTACT_LENGTH",
    "COVERED_LENGTH",
    "COVERS_LENGTH",
    "ESSENTIALS_CUT_NAMES",
    "ESSENTIAL_ITEM_TEXT_LENGTH",
    "ESSENTIAL_LIST_CAP",
    "FAR_FUTURE_DAYS",
    "INSURER_NAME_LENGTH",
    "POLICY_SCOPE",
    "REFERENCE_LENGTH",
    "WAITING_PERIOD_LENGTH",
    "EssentialItem",
    "NoSuchPolicy",
    "NotAPolicy",
    "NotAPolicyReference",
    "NotTheirsToSetAPolicy",
    "Policy",
    "PolicyPeriodState",
    "PolicyStatus",
    "PolicyType",
    "current_policies",
    "may_set_a_policy",
    "policy_draft",
    "policy_period_date",
    "policy_period_state",
    "set_a_policy",
]

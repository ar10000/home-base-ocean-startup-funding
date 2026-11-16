"""Status and freshness rules for opportunities.

Every public function quotes the rule IDs it implements, as listed in
docs/rules/opportunities.yaml. Pure functions only: `today` is always passed in.
"""

from collections.abc import Iterable
from datetime import date

from home_base.config import (
    DEADLINE_AS_DAYS_LEFT_MAX,
    EVIDENCE_MAX_AGE_MONTHS,
    NEAR_DEADLINE_DAYS,
    REVIEW_INTERVAL_DAYS,
    REVIEW_INTERVAL_DAYS_NEAR_DEADLINE,
)
from home_base.core.dates import days_left, months_before
from home_base.core.errors import OpportunityStateError, VerificationError
from home_base.core.vocabulary import FitStatus
from home_base.modules.opportunities.domain import (
    DeadlineDisplay,
    DeadlineKind,
    Evidence,
    FreshnessState,
    Month,
    OpportunityStatus,
    ReloadEffects,
    ReloadOutcome,
    SourcedValue,
    SourceResolution,
    Verification,
    VerificationMethod,
)

# D-41: fit order in the Opportunities list.
_FIT_ORDER = (FitStatus.CONFIRMED, FitStatus.POSSIBLE, FitStatus.NOT_ELIGIBLE)


def last_verified_date(verifications: Iterable[Verification], today: date) -> date | None:
    """The date of the latest manual check, or None if there has never been one.

    Rule FRS-01: each opportunity carries a last verified date, set only by a
    manual check. Automated checks are kept in history but never count here.
    """
    manual: list[date] = []
    for v in verifications:
        if v.verified_on > today:
            raise VerificationError(f"verification dated in the future: {v.verified_on}")
        if v.method is VerificationMethod.MANUAL:
            manual.append(v.verified_on)
    return max(manual, default=None)


def review_interval_days(deadline: date | None, today: date) -> int:
    """How many days a verification stays valid.

    Rule FRS-02: review interval is 14 days.
    Rule FRS-03: review interval is 7 days when the deadline is within 30 days.
    "Within 30 days" includes day 30 and today (decision D-15 in docs/decisions.md).
    A call with no deadline ("Rolling") keeps the default interval.
    """
    if deadline is not None and 0 <= days_left(deadline, today) <= NEAR_DEADLINE_DAYS:
        return REVIEW_INTERVAL_DAYS_NEAR_DEADLINE
    return REVIEW_INTERVAL_DAYS


def freshness_state(
    last_verified: date | None, deadline: date | None, today: date
) -> FreshnessState:
    """Whether an opportunity is current, due a re-check, or closed.

    Rule FRS-04: past its interval gives Re-check due (listed with a flag,
    excluded from priorities and Today's deadlines).
    Rule FRS-05: a passed deadline gives Closed (hidden, kept in history).
    The deadline day itself is still open. The interval has passed once more
    days than the interval have gone by since the check (decision D-15).
    An opportunity never checked by hand is Re-check due (decision D-17).
    """
    if deadline is not None and days_left(deadline, today) < 0:
        return FreshnessState.CLOSED
    if last_verified is None:
        return FreshnessState.RECHECK_DUE
    if last_verified > today:
        raise VerificationError(f"last verified date is in the future: {last_verified}")
    if (today - last_verified).days > review_interval_days(deadline, today):
        return FreshnessState.RECHECK_DUE
    return FreshnessState.CURRENT


def opportunity_status(
    opening: date | None, expected_month: Month | None, deadline: date | None, today: date
) -> OpportunityStatus:
    """Whether an opportunity is open, upcoming or closed, calculated (decision D-18).

    Rule UPC-01: status is Open, Upcoming or Closed.
    An official opening date makes it Open from that day; it wins over an
    expected month. With only an expected month it stays Upcoming until a check
    records the published call's opening date. With neither, it is an open call.
    Closed from the day after the deadline; the deadline day is still open (D-15).
    """
    if deadline is not None and days_left(deadline, today) < 0:
        return OpportunityStatus.CLOSED
    if opening is not None:
        return OpportunityStatus.OPEN if opening <= today else OpportunityStatus.UPCOMING
    if expected_month is not None:
        return OpportunityStatus.UPCOMING
    return OpportunityStatus.OPEN


def based_on_last_edition(
    opening: date | None, expected_month: Month | None, deadline: date | None, today: date
) -> bool:
    """Whether fit and readiness are labelled "based on last edition".

    Rule UPC-03: until the call is published, fit and readiness use the last
    edition, labelled as such. The opportunity's own record holds the last
    edition's requirements and questions; the call is unpublished while it is
    Upcoming with only an expected month, and a check that records the official
    opening date publishes it (decisions D-18, D-42).
    """
    if opening is not None:
        return False  # a recorded official opening date means the call is published
    status = opportunity_status(None, expected_month, deadline, today)
    return status is OpportunityStatus.UPCOMING


def evidence_counts(evidence: Evidence, today: date) -> bool:
    """Whether a piece of evidence is recent enough to back an expected opening.

    Rule UPC-05: evidence older than 18 months does not count.
    Age is from the evidence's own date; exactly 18 calendar months still counts
    (decision D-20).
    """
    if evidence.dated > today:
        raise VerificationError(f"evidence dated in the future: {evidence.dated}")
    return evidence.dated >= months_before(today, EVIDENCE_MAX_AGE_MONTHS)


def upcoming_is_shown(
    opening: date | None,
    expected_month: Month | None,
    evidence: Iterable[Evidence],
    today: date,
) -> bool:
    """Whether an upcoming opportunity may be listed.

    Rule UPC-02: Upcoming is shown only with an official opening date, or an
    expected month backed by evidence.
    Rule UPC-05: only evidence that still counts backs it, so an opportunity whose
    evidence is all too old stays hidden until a check adds newer evidence (D-21).
    """
    if opening is not None:
        return True
    if expected_month is None:
        return False
    return any(evidence_counts(e, today) for e in evidence)


def _upcoming_opening(opening: date | None, expected_month: Month | None, today: date) -> date:
    """The day an upcoming opportunity is expected to open; refuses one that is not upcoming."""
    if opening is not None:
        if opening <= today:
            raise OpportunityStateError(
                f"opening date {opening} has been reached: the call is open"
            )
        return opening
    if expected_month is None:
        raise OpportunityStateError("no opening date or expected month: not an upcoming call")
    return expected_month.first_day


def upcoming_review_interval_days(
    opening: date | None, expected_month: Month | None, today: date
) -> int:
    """How many days a verification of an upcoming opportunity stays valid.

    Rule UPC-04: review every 14 days, every 7 when the opening is within 30 days.
    "Within 30 days" includes day 30 and today (D-15). For an expected month the
    opening counts as its 1st, and the 7-day interval also applies during the
    month itself (decision D-19).
    """
    reference = _upcoming_opening(opening, expected_month, today)
    if days_left(reference, today) <= NEAR_DEADLINE_DAYS:
        return REVIEW_INTERVAL_DAYS_NEAR_DEADLINE
    return REVIEW_INTERVAL_DAYS


def upcoming_freshness_state(
    last_verified: date | None, opening: date | None, expected_month: Month | None, today: date
) -> FreshnessState:
    """Whether an upcoming opportunity is current or due a re-check.

    Rule UPC-04: an expected month that passes with no call published gives
    Re-check due, from the 1st of the next month (decision D-19). A recorded
    opening date means the call is published. Otherwise freshness works as for
    open calls: never checked by hand, or past the interval, gives Re-check due.
    """
    interval = upcoming_review_interval_days(opening, expected_month, today)
    if last_verified is not None and last_verified > today:
        raise VerificationError(f"last verified date is in the future: {last_verified}")
    if opening is None and expected_month is not None and today >= expected_month.first_day_after:
        return FreshnessState.RECHECK_DUE
    if last_verified is None or (today - last_verified).days > interval:
        return FreshnessState.RECHECK_DUE
    return FreshnessState.CURRENT


def resolve_sources(claims: Iterable[SourcedValue]) -> SourceResolution:
    """Pick the value to show when sources may disagree.

    Rule FRS-07: when sources disagree, the official one wins; with no official
    source, the opportunity is Re-check due. Two official sources that disagree
    also give Re-check due (decision D-16 in docs/decisions.md).
    """
    items = list(claims)
    values = {c.value for c in items}
    if len(values) <= 1:
        return SourceResolution(value=next(iter(values), None), recheck_due=False)
    official = {c.value for c in items if c.official}
    if len(official) == 1:
        return SourceResolution(value=official.pop(), recheck_due=False)
    return SourceResolution(value=None, recheck_due=True)


def list_sort_key(
    fit: FitStatus, deadline_or_opening: date | None, blue_specific: bool, name: str
) -> tuple[int, bool, date, bool, str]:
    """Sort key for the Opportunities list, within one goal group.

    Rule SCP-02: when fit and deadline are equal, blue-specific sorts before
    all-sector. The full order is fit (Confirmed, Possible, Not eligible), then the
    earliest deadline (or opening, for an upcoming call; no date last), then
    blue-specific first, then name A to Z (decision D-41). Grouping by goal
    comes before this and belongs to INT-03.
    """
    return (
        _FIT_ORDER.index(fit),
        deadline_or_opening is None,
        deadline_or_opening or date.max,
        not blue_specific,
        name.casefold(),
    )


def reload_effects(outcome: ReloadOutcome) -> ReloadEffects:
    """What a reload outcome triggers.

    Rule FRS-06: a change found in a re-check is logged and the opportunity's matches
    are recalculated. Under D-46 a re-check is a reviewed seed file change, applied by
    the reload: an added or changed opportunity is logged and recalculated; an archived
    one is logged and keeps its last matches (it leaves the lists); an unchanged one
    triggers nothing.
    """
    changed = outcome in (ReloadOutcome.ADDED, ReloadOutcome.CHANGED)
    return ReloadEffects(audit=outcome is not ReloadOutcome.UNCHANGED, recalculate=changed)


def deadline_display(deadline: date | None, today: date) -> DeadlineDisplay:
    """How the deadline is shown.

    Rule SCP-03: days left when the deadline is 30 days or fewer away, otherwise
    its date; "Rolling" when there is none. A passed deadline shows its date (D-56).
    """
    if deadline is None:
        return DeadlineDisplay(DeadlineKind.ROLLING)
    left = days_left(deadline, today)
    if 0 <= left <= DEADLINE_AS_DAYS_LEFT_MAX:
        return DeadlineDisplay(DeadlineKind.DAYS_LEFT, left)
    return DeadlineDisplay(DeadlineKind.DATE)

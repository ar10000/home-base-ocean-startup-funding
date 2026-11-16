"""Calendar helpers shared by every module.

Rules never call now(): callers pass `today` in, computed once per request with
`local_today`. That keeps every rule a pure function and every test deterministic.
"""

import calendar
from datetime import date, datetime

from home_base.config import APP_TIMEZONE
from home_base.core.errors import ClockError


def local_today(now: datetime) -> date:
    """Today's calendar date in Lisbon, from a timezone-aware instant.

    Rule PRI-07: day counts use the Lisbon calendar date.
    """
    if now.tzinfo is None:
        raise ClockError("now must be timezone-aware")
    return now.astimezone(APP_TIMEZONE).date()


def days_left(deadline: date, today: date) -> int:
    """Calendar days from today to the deadline; negative once it has passed.

    Rule PRI-07: Days left = deadline date minus today in Lisbon, rounded down.
    Both arguments are calendar dates, so the result is already a whole number.
    """
    return (deadline - today).days


def months_before(day: date, months: int) -> date:
    """The same day of the month, `months` calendar months earlier.

    When that day does not exist (31 February), the month's last day is used
    (decision D-20, for the 18-month evidence limit of rule UPC-05).
    """
    if months < 0:
        raise ClockError(f"months must not be negative, got {months}")
    index = day.year * 12 + (day.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))

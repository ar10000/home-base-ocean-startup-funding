"""Per-request time, tracing and caller, passed into every service (architecture rule 10).

The API builds one per request: `at` is the instant (UTC), `today` the calendar date
the rules use (Lisbon, via `local_today`). Services never read a clock themselves.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Clock:
    at: datetime
    today: date
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class Caller:
    """The signed-in founder: their company (the tenant) and user ID, from the session,
    never from a request body (handbook section 13)."""

    company_id: uuid.UUID
    user_id: uuid.UUID

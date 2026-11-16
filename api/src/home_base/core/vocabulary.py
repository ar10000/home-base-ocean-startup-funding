"""Vocabulary shared by several modules (handbook section 3: core holds shared types).

Matching owns the rules that produce these values; Today and the API read them.
"""

from enum import StrEnum


class FitStatus(StrEnum):
    """Fit of a company for one opportunity (spec: Fit status per opportunity)."""

    CONFIRMED = "confirmed"
    POSSIBLE = "possible"
    NOT_ELIGIBLE = "not_eligible"


class Decision(StrEnum):
    """The founder's decision on a match (spec: Founder decisions)."""

    NONE = "none"
    PURSUING = "pursuing"
    LATER = "later"
    NOT_FOR_US = "not_for_us"


class Operator(StrEnum):
    """How a hard requirement compares the company fact with its value."""

    EQUALS = "equals"
    ONE_OF = "one_of"
    NOT_ONE_OF = "not_one_of"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


class OpportunityType(StrEnum):
    """What kind of opportunity it is; one opportunity may have several (decision D-43)."""

    GRANT = "grant"
    ACCELERATOR = "accelerator"  # accelerator or incubator
    TESTBED_OR_PILOT = "testbed_or_pilot"
    PROCUREMENT_CHALLENGE = "procurement_challenge"  # procurement or innovation challenge
    PRIZE = "prize"  # prize or competition
    INVESTOR_PROGRAMME = "investor_programme"  # investor programme with a call

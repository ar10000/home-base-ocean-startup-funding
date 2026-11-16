"""Named business constants.

Every value here comes from the Phase 1 spec and carries the rule ID that owns it.
Rules import these; they never hard-code numbers.
"""

from typing import Final
from zoneinfo import ZoneInfo

# PRI-07: days left are counted in Lisbon calendar dates.
APP_TIMEZONE: Final = ZoneInfo("Europe/Lisbon")

# FIT-04: below this many hard rules, a match is never Confirmed.
MIN_HARD_RULES_FOR_CONFIDENT_FIT: Final = 2

# FRS-02, UPC-04: default review interval for an opportunity's source.
REVIEW_INTERVAL_DAYS: Final = 14

# FRS-03, UPC-04: shorter review interval when the deadline (or the opening) is close.
REVIEW_INTERVAL_DAYS_NEAR_DEADLINE: Final = 7

# FRS-03, UPC-04: "close" means within this many days.
NEAR_DEADLINE_DAYS: Final = 30

# SCP-03: a deadline this many days away or fewer is shown as days left (D-56).
DEADLINE_AS_DAYS_LEFT_MAX: Final = 30

# UPC-05: evidence for an expected opening counts for this many calendar months.
EVIDENCE_MAX_AGE_MONTHS: Final = 18

# PRG-04: the company fact fields hard rules can check (spec: Requirement types; D-26).
# "applicant_form" is the consortium-need fact (REQ-05).
HARD_RULE_FACT_KEYS: Final = frozenset(
    {"country", "sector", "legal_form", "company_age", "team_size", "trl", "applicant_form"}
)

# The founder's journey stages, in order (spec: Today > Stage; decision D-78, from the
# wireframes' Journey screen, confirmed by Andrew 2026-11-16). Set by the founder in Phase 1.
STAGES: Final = (
    ("idea", "Idea"),
    ("validation", "Validation"),
    ("foundations", "Foundations"),
    ("prototype", "Prototype"),
    ("pilot", "Pilot"),
    ("non_dilutive_funding", "Non-dilutive funding"),
    ("raise_prep", "Raise prep"),
    ("first_round", "First round"),
    ("growth", "Growth"),
)
# REQ-09: the text facts with a fixed list of values (decision D-76), as (value, label).
# Both the company profile and the seed files may only use these values, so a call's rule
# and a company's fact always speak the same words. Countries: the 27 EU Member States
# (D-45), as the seed files write them, plus "OTHER" for a company outside the EU.
EU_COUNTRIES: Final = (
    ("AT", "Austria"), ("BE", "Belgium"), ("BG", "Bulgaria"), ("HR", "Croatia"),
    ("CY", "Cyprus"), ("CZ", "Czechia"), ("DK", "Denmark"), ("EE", "Estonia"),
    ("FI", "Finland"), ("FR", "France"), ("DE", "Germany"), ("GR", "Greece"),
    ("HU", "Hungary"), ("IE", "Ireland"), ("IT", "Italy"), ("LV", "Latvia"),
    ("LT", "Lithuania"), ("LU", "Luxembourg"), ("MT", "Malta"), ("NL", "Netherlands"),
    ("PL", "Poland"), ("PT", "Portugal"), ("RO", "Romania"), ("SK", "Slovakia"),
    ("SI", "Slovenia"), ("ES", "Spain"), ("SE", "Sweden"),
)  # fmt: skip
FACT_VALUES: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "country": (*EU_COUNTRIES, ("OTHER", "Outside the EU")),
    # Sectors of the EU Blue Economy Report: established, then emerging (Andrew, D-76).
    "sector": (
        ("marine_living_resources", "Marine living resources (fisheries, aquaculture, seaweed)"),
        ("marine_non_living_resources", "Marine non-living resources"),
        ("marine_renewable_energy", "Marine renewable energy"),
        ("port_activities", "Port activities"),
        ("shipbuilding_and_repair", "Shipbuilding and repair"),
        ("maritime_transport", "Maritime transport"),
        ("coastal_tourism", "Coastal tourism"),
        ("blue_biotechnology", "Blue biotechnology"),
        ("ocean_energy", "Ocean energy"),
        ("desalination", "Desalination"),
        ("maritime_defence_and_security", "Maritime defence and security"),
        ("research_and_education", "Research and education"),
        ("marine_infrastructure_and_robotics", "Marine infrastructure and robotics"),
        ("other", "Other (not ocean-specific)"),
    ),
    "legal_form": (
        ("not_incorporated", "Not yet incorporated"),
        ("sole_trader", "Sole trader (ENI)"),
        ("private_limited", "Private limited company (Lda, Unipessoal Lda)"),
        ("public_limited", "Public limited company (S.A.)"),
        ("cooperative", "Cooperative"),
        ("non_profit", "Non-profit association or foundation"),
    ),
    # REQ-05: the consortium-need fact.
    "applicant_form": (("alone", "Alone"), ("consortium", "In a consortium")),
}

# REQ-06, REQ-07: optional founder facts hard rules may check (decision D-44). Kept out of
# HARD_RULE_FACT_KEYS so PRG-04's milestone never needs personal data. "founder_age" is
# derived from the stored birth date on each call's deadline.
FOUNDER_FACT_KEYS: Final = frozenset({"founder_age", "woman_founder", "woman_ceo"})

# REQ-07: founder facts are personal data: never logged, never sent to the AI (D-44).
PERSONAL_FACT_KEYS: Final = FOUNDER_FACT_KEYS | {"youngest_founder_birth_date"}

# PRI-10: minutes per Today task type (spec table plus decision D-27). Keys are TaskType values.
TIME_ESTIMATE_MINUTES: Final = {
    "add_fact": 10,
    "review_drafts": 5,
    "start_application": 20,
    "decide": 5,
    "check_goals": 5,
    "answer_one_question": 10,
    "next_answer": 10,
    "back_on_list": 5,
}

# PRI-11: a Confirmed match closing within this many days puts Today in Applying mode.
APPLYING_CLOSES_WITHIN_DAYS: Final = 30

# DEC-03: Later returns this many days before the deadline or opening.
LATER_RETURNS_DAYS_BEFORE: Final = 30

# PRI-01, PRI-02: an application "due within" this many days.
APPLICATION_DUE_WITHIN_DAYS: Final = 14

# PRI-03: a Possible match "closes within" this many days.
POSSIBLE_CLOSES_WITHIN_DAYS: Final = 21

# PRI-04: a Confirmed match with no application "closes within" this many days.
CONFIRMED_CLOSES_WITHIN_DAYS: Final = 30

# PRI-09: how many tasks "Needs attention" shows after the one thing today.
NEEDS_ATTENTION_COUNT: Final = 3

# PRI-14: an upcoming opportunity "opens within" this many days.
OPENING_SOON_DAYS: Final = 30

# PRI-18: how many opportunities "Opening soon" shows in preparing mode.
OPENING_SOON_COUNT: Final = 3

# PRI-16: intent untouched for more than this many days gives "Check your goals".
INTENT_STALE_DAYS: Final = 90

# INT-03: which goals each opportunity type serves (decision D-43). Keys are
# OpportunityType values, goals are Goal values.
GOALS_SERVED_BY_TYPE: Final = {
    "grant": frozenset({"non_dilutive_funding"}),
    "accelerator": frozenset({"accelerator_place"}),
    "testbed_or_pilot": frozenset({"pilot_or_test_site"}),
    "procurement_challenge": frozenset({"pilot_or_test_site", "first_customers"}),
    "prize": frozenset({"non_dilutive_funding"}),
    "investor_programme": frozenset({"investment"}),
}

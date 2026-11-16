"""Typed domain errors. The API layer maps them to RFC 9457 problem responses."""


class DomainError(Exception):
    """Base class for errors raised by domain and rule code."""


class EligibilityRuleError(DomainError):
    """A requirement cannot be evaluated as written, for example a numeric rule on a text fact."""


class VerificationError(DomainError):
    """A verification record breaks the freshness rules, for example an automated check."""


class ClockError(DomainError):
    """A date or time was passed in a form the rules do not accept."""


class OpportunityStateError(DomainError):
    """A rule was asked about an opportunity in a status it does not cover."""


class IntentError(DomainError):
    """An intent record breaks the intent rules, for example no goals."""


class DecisionError(DomainError):
    """A founder decision breaks the decision rules, for example a reason on Pursuing."""


class SeedError(DomainError):
    """A seed opportunity file breaks the seed schema (handbook section 11)."""


class TenantError(DomainError):
    """A row was written for, or read from, a company other than the session's."""


class AuditError(DomainError):
    """An audit event breaks the audit rules, for example a founder fact's value in it."""


class FactError(DomainError):
    """A company or founder fact breaks the fact rules, for example an unknown key."""


class ApplicationError(DomainError):
    """An application change breaks the application rules, for example a closed workspace."""


class NotFoundError(DomainError):
    """The record asked for does not exist for this company."""


class NotSignedInError(DomainError):
    """The request has no signed-in founder."""


class NotOnboardedError(DomainError):
    """The signed-in user has no company yet; onboarding comes first."""


class OnboardingError(DomainError):
    """Onboarding cannot be done, for example the user already has a company."""


class StageError(DomainError):
    """A journey stage that is not in the list (D-78)."""

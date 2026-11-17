"""Application rules.

Every public function quotes the rule IDs it implements, as listed in
docs/rules/today.yaml and docs/rules/applications.yaml. Pure functions only.
"""

from collections.abc import Collection, Iterable

from home_base.modules.audit.domain import Actor


def approvable(text: str) -> bool:
    """Rule PRG-05: an answer can only be approved when its text is not blank (D-72)."""
    return text.strip() != ""


def unusable_citations[T](cited: Iterable[T], usable: Collection[T]) -> list[T]:
    """Rule DRF-01: a draft may only use approved company facts. The cited facts that
    are not usable (approved, current, the company's own), each once, in cited order."""
    return [c for c in dict.fromkeys(cited) if c not in usable]


def draft_citations[T](sentences: Iterable[Iterable[T]]) -> list[T]:
    """Rule DRF-02: every draft stores links to the facts it used: every fact any of
    its sentences cites, each once, in the order first cited (D-81)."""
    return list(dict.fromkeys(c for sentence in sentences for c in sentence))


def may_mark_submitted(actor: Actor) -> bool:
    """Rule DRF-03: nothing is submitted from the platform; only the founder marks an
    application submitted."""
    return actor is Actor.FOUNDER

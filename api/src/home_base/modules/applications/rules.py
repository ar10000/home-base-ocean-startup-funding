"""Application rules.

Every public function quotes the rule IDs it implements, as listed in
docs/rules/today.yaml. Pure functions only.
"""


def approvable(text: str) -> bool:
    """Rule PRG-05: an answer can only be approved when its text is not blank (D-72)."""
    return text.strip() != ""

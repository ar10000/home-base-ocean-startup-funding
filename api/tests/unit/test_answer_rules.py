"""Rule PRG-05 at its edges: blank is empty or whitespace only (D-72)."""

import pytest

from home_base.modules.applications.rules import approvable


@pytest.mark.parametrize("text", ["x", " x ", "0", "\N{NO-BREAK SPACE}x"])
def test_prg_05_text_with_any_visible_character_is_approvable(text: str) -> None:
    assert approvable(text)


@pytest.mark.parametrize("text", ["", " ", "\n", "\t \r\n", "\N{NO-BREAK SPACE}", "\N{EM SPACE}"])
def test_prg_05_blank_text_is_not_approvable(text: str) -> None:
    assert not approvable(text)

import pytest


def _foo(string: str) -> str:
    return string.upper()


def test_foo():
    with pytest.raises(ValueError) as e:
        raise ValueError(_foo("Boooo!"))
    assert str(e.value) == "BOOOO!"


def test_bar():
    assert 1 == 1
    # assert 1 == 2  # uncomment for testing job failure

import pytest


def _foo(string: str) -> str:
    return string.upper()


def test_foo():
    with pytest.raises(ValueError) as e:
        raise ValueError(_foo("Boooo!"))
    assert str(e.value) == "BOOOO!"

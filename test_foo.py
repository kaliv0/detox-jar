import pytest


def test_foo():
    with pytest.raises(ValueError) as e:
        raise ValueError("Boooo!")
    assert str(e.value) == "Boooo!"

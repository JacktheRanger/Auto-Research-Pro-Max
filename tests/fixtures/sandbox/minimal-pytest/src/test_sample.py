from sample import add, multiply


def test_add() -> None:
    assert add(1, 2) == 3


def test_multiply() -> None:
    assert multiply(3, 4) == 12

"""Intentional failures: compare the diagnostic output locally and with xdist."""


def test_explicit_example():
    try:
        try:
            raise ValueError(11)
        except Exception as first:
            raise ValueError(12) from first
    except Exception as second:
        raise ValueError(13) from second


def test_implicit_example():
    try:
        try:
            raise ValueError(21)
        except Exception:
            raise ValueError(22)
    except Exception:
        raise ValueError(23)

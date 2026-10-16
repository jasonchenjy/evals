import os
assert os.environ.get("PYTEST_XDIST_WORKER") == "gw0"
def fail():
    try:
        raise ValueError("worker-inner-503")
    except ValueError as e:
        raise RuntimeError("worker-outer-509") from e

def test_remote():
    fail()

# Exception serialization should include chained exceptions

Given these tests:

```python
def test_chained_exception_with_from():
    try:
        try:
            raise ValueError(11)
        except Exception as e1:
            raise ValueError(12) from e1
    except Exception as e2:
        raise ValueError(13) from e2


def test_chained_exception_without_from():
    try:
        try:
            raise ValueError(21)
        except Exception:
            raise ValueError(22)
    except Exception:
        raise ValueError(23)
```

Without pytest-xdist, the output shows the whole exception trace: ValueError(11),
ValueError(12), and ValueError(13), with the direct-cause relationships; the second
test shows ValueError(21), ValueError(22), and ValueError(23), with the messages
explaining that another exception occurred during handling of the previous one.

With pytest-xdist (`-n auto`), only the last exception in each test is displayed:
ValueError(13) and ValueError(23). The distributed output should retain the
exception information and relationships shown in the local output.

The reporter used pytest 4.0.2 and pytest-xdist 1.25.0; the posted output identifies
Python 3.6.7 on Linux. These are historical reproduction details, not instructions
to replace the provided environment.

Investigate the repository and implement a source-code fix for this issue.

# Preserve exception information in distributed test runs

Running a failing pytest test locally displays the complete chain of exceptions,
but running the same test using pytest-xdist only displays the final exception.

For example, ValueError(11) causes ValueError(12), which then causes ValueError(13).
The distributed report should preserve the earlier exceptions and their
relationships, consistent with the local report.

Investigate the repository and implement a source-code fix without breaking
existing pytest behavior.

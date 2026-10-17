Repair this small order-processing service. Input has the form `item|quantity`.
The result must have `item` (trimmed, nonempty text), `quantity` (an integer from
1 through 100), and `total` (quantity times 3). Whitespace around both fields is
allowed. Malformed input and invalid values must raise ValueError.

Investigate parser.py, validator.py, service.py, and tests/test_public.py. Preserve
their responsibilities: parsing splits the fields, normalization trims/converts,
validation checks the normalized values, and the service combines them.
Introduce a new `src/normalization.py` helper and update the existing source as
needed. Do not change the public tests or dependencies. Work only on Python
source under src/ for the final submission. Temporary debugging files may live
outside src/ and are not submitted.

Run `python -m unittest discover -s tests -v`, inspect the feedback, and check your
final changes with Git. The workspace is persistent; leave the changes in place.
The controller collects the final source and verifies it in a fresh environment.

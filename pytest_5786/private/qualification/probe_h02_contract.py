"""Bounded H02 diagnostic probes. No assertions here change Eval scoring.

Invoke with the pinned Python/PYTHONPATH in a clean reviewed control workspace.
--produce writes exact JSON inputs and observable outcomes; --consume reads
unmodified payloads from each of the four producer implementations.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

from _pytest._code.code import ExceptionInfo, ReprEntry
from _pytest.reports import CollectReport, TestReport
from _pytest.reports import pytest_report_from_serializable, pytest_report_to_serializable


class Unknown(ReprEntry):
    """Renderable producer-side subtype unsupported by the default decoder."""


def build(kind, chained=False):
    try:
        if chained:
            try:
                raise ValueError("h02-cause-701")
            except ValueError as cause:
                raise RuntimeError("h02-final-709") from cause
        assert False, "h02-single-719"
    except (AssertionError, RuntimeError):
        value = ExceptionInfo.from_current().getrepr(style="short")
    args = dict(nodeid="probe_case.py::test_case", outcome="failed", longrepr=value,
                sections=[("Captured stdout call", "h02-captured-727")])
    if kind is TestReport:
        return kind(location=("probe_case.py", 0, "test_case"), keywords={},
                    when="call", duration=0.125, **args)
    return kind(result=[], **args)


def observe(data, kind=None):
    try:
        restored = (kind._from_json(copy.deepcopy(data)) if kind else
                    pytest_report_from_serializable(copy.deepcopy(data)))
        if restored is None:
            return {"status": "unhandled"}
        return {"status": "restored", "report_type": type(restored).__name__,
                "failed": restored.failed, "text": restored.longreprtext,
                "crash_message": restored.longrepr.reprcrash.message,
                "capstdout": restored.capstdout,
                "item_index": getattr(restored, "item_index", None),
                "worker_id": getattr(restored, "worker_id", None)}
    except Exception as error:
        return {"status": "exception", "exception_type": type(error).__name__,
                "message": str(error)}


def produce(output):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    payloads = []
    for kind in [TestReport, CollectReport]:
        for chained in [False, True]:
            report = build(kind, chained)
            data = json.loads(json.dumps(pytest_report_to_serializable(report)))
            # Exactly the top-level metadata added by the xdist testreport sender.
            data.update(item_index=7, worker_id="gw0")
            case = kind.__name__ + ("_chain" if chained else "_single")
            payloads.append({"id": case, "payload": data, "source_text": report.longreprtext,
                             "source_crash": report.longrepr.reprcrash.message})
            records.append({"id": case + "_valid", "input": data,
                            "expected": "same-codec report, structured consumption and metadata preserved; base chain bug remains measurable",
                            "actual": observe(data)})

        # Faithful reproduction of the historical mutation: no wire round trip
        # is required, and the classmethod, rather than dispatch hook, is called.
        original = build(kind)
        data = original._to_json()
        data["longrepr"]["reprtraceback"]["reprentries"][0]["type"] = "Unknown"
        records.append({"id": kind.__name__ + "_historical_outer_mutation", "input": copy.deepcopy(data),
                        "expected": "Historical layout assertion: RuntimeError containing INTERNALERROR: Unknown entry type returned: Unknown",
                        "actual": observe(data, kind)})

        # Consumer-facing rejection probe: introduce an unsupported representation
        # on the producer object. No serialized dictionary path is selected.
        report = build(kind)
        entry = report.longrepr.reprtraceback.reprentries[0]
        report.longrepr.reprtraceback.reprentries[0] = Unknown(
            lines=entry.lines, reprfuncargs=entry.reprfuncargs, reprlocals=entry.reprlocals,
            filelocrepr=entry.reprfileloc, style=entry.style)
        data = json.loads(json.dumps(pytest_report_to_serializable(report)))
        records.append({"id": kind.__name__ + "_unsupported_producer_entry", "input": data,
                        "expected": "Reject an actually consumed unsupported representation with an informative RuntimeError",
                        "actual": observe(data)})

        data = pytest_report_to_serializable(build(kind))
        data["longrepr"]["reprtraceback"]["reprentries"][0]["data"]["lines"] = ["outer-copy-only-733"]
        records.append({"id": kind.__name__ + "_wellformed_outer_edit", "input": copy.deepcopy(data),
                        "expected": "Observation only: identifies whether this outer copy is authoritative",
                        "actual": observe(data)})

        data = pytest_report_to_serializable(build(kind))
        data["_report_type"] = "UnsupportedReport"
        records.append({"id": kind.__name__ + "_unknown_report_tag", "input": copy.deepcopy(data),
                        "expected": "Existing default hook rejects a recognized envelope with unsupported report tag; exact wire tag is diagnostic",
                        "actual": observe(data)})
        data = pytest_report_to_serializable(build(kind))
        del data["longrepr"]
        records.append({"id": kind.__name__ + "_missing_required_value", "input": copy.deepcopy(data),
                        "expected": "Observation only: malformed-input handling has no universal RuntimeError contract",
                        "actual": observe(data)})
    (output / "payloads.json").write_text(json.dumps(payloads, indent=2) + "\n")
    (output / "observations.json").write_text(json.dumps(records, indent=2) + "\n")
    # Only the documented probe contract is asserted, never the H02 outcome.
    for record in records:
        if record["id"].endswith("_unsupported_producer_entry"):
            actual = record["actual"]
            assert actual["status"] == "exception" and actual["exception_type"] == "RuntimeError"
            assert "Unknown entry type returned: Unknown" in actual["message"]
    print(json.dumps({"observations": len(records), "unsupported_entry_rejection": "passed"}))


def consume(producers, output):
    rows = []
    for path in sorted(producers.glob("*/payloads.json")):
        for source in json.loads(path.read_text()):
            actual = observe(source["payload"])
            rows.append({"producer": path.parent.name, "id": source["id"],
                         "expected": "Cross-codec observation only; not a mandatory interoperability requirement",
                         "actual": actual,
                         "matches_producer_source_text": actual.get("text") == source["source_text"]})
    assert len(rows) == 16
    output.write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"cross_codec_observations": len(rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--produce", type=Path)
    action.add_argument("--consume", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.produce:
        produce(args.produce)
    else:
        consume(args.consume, args.output)

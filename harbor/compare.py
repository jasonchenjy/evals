"""Compare original, existing Runtime and actual Harbor grading evidence."""
import argparse, hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument("raw",type=Path);args=parser.parse_args()
original=json.loads((root.parent/"pytest_5786/private/qualification/summary.json").read_text())
runtime=json.loads((root.parent/"runtime/evidence/mac_mini_20261016/qualification_summary.json").read_text())
ref={x["control"]:x for x in original["controls"]}; rt={x["control"]:x for x in runtime["controls"]}
summary=json.loads((args.raw/"summary.json").read_text()); assert len(summary)==len(ref)==7
catalog=json.loads((root.parent/"pytest_5786/private/test_catalog.json").read_text())
assert next(x for x in catalog if x["id"]=="H02")["mandatory"] is False
rows=[]; differences=[];original_differences=[]; count=0
for item in summary:
    name=item["control"];assert item["expectation_met"], name
    actual=json.loads((args.raw/name/"verifier/grader/result.json").read_text())
    assert actual["infrastructure_status"]=="ok" and actual["submission_status"]=="accepted"
    assert actual["overall_resolved"]==ref[name]["expected_overall"]
    checks={t["id"]:t["status"] for t in actual["tests"]}
    dims={k:v["satisfied"] for k,v in actual["dimensions"].items()}
    if name=="historical": assert dims["original_bug_resolution"] and not dims["non_regression"]
    for key,value in checks.items():
        count+=1
        if rt[name]["checks"].get(key)!=value: differences.append(dict(control=name,check=key,runtime=rt[name]["checks"].get(key),harbor=value))
        if ref[name]["checks"].get(key)!=value: original_differences.append(dict(control=name,check=key,original=ref[name]["checks"].get(key),harbor=value))
    rows.append(dict(control=name,overall=actual["overall_resolved"],dimensions=dims,checks=checks,infrastructure_status=actual["infrastructure_status"]))
result=dict(baseline_sha256={str(p.relative_to(root.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root.parent/"pytest_5786/private/qualification/summary.json",root.parent/"runtime/evidence/mac_mini_20261016/qualification_summary.json"]},controls=rows,check_count=count,all_expectations_met=True,runtime_differences=differences,original_platform_differences=original_differences,H02_diagnostic_only=True,grader_sha256=hashlib.sha256((root.parent/"pytest_5786/private/grader.py").read_bytes()).hexdigest(),comparison_runtime="runtime/evidence/mac_mini_20261016/qualification_summary.json",comparison_original="pytest_5786/private/qualification/summary.json")
(root/"evidence/qualification-comparison.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))

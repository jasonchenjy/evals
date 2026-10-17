"""Eval-only experiment: reuse the existing isolated grader on archived patches."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'runtime'))
from core import Package, save
from container_sandbox import ContainerSandbox
from grading import grade
from submission import assert_applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval', type=Path, default=HERE.parent)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--controls', nargs='+', default=[
        'noop', 'historical', 'complete', 'alternative', 'last_only',
        'testreport_only', 'text_only', 'first_real',
        'chain_assumed', 'links_omitted', 'sections_omitted'])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    package = Package(args.eval, REPO.parent / 'pytest')
    sandbox = ContainerSandbox('/usr/local/bin/docker',
        'unix:///private/tmp/pytest5786-colima/default/docker.sock',
        REPO / 'harbor/tools/docker',
        'sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12', output / 'workers')
    sandbox.base.env['DOCKER_BUILDKIT'] = '0'
    summary = dict(model_calls=0, provenance=package.provenance, controls=[])
    for name in args.controls:
        if name == 'first_real':
            patch = REPO / 'harbor/evidence/pytest5786-stage3-20261017T075426Z/codex/submission/submission.patch'
        elif name in ('chain_assumed', 'links_omitted', 'sections_omitted'):
            patch = HERE / 'controls' / (name + '.patch')
        else:
            patch = HERE.parent / 'private/oracle' / (name + '.patch')
        expected_dir = output / 'independent-apply' / name
        package.prepare(expected_dir)
        expected = assert_applied(package, patch, expected_dir)
        result = grade(package, sandbox, patch, output / name, expected)
        entry = dict(control=name, patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
            infrastructure_status=result['infrastructure_status'], submission_status=result['submission_status'],
            overall=result['overall_resolved'],
            dimensions={k:v['satisfied'] for k,v in result['dimensions'].items()},
            checks={x['id']:x['status'] for x in result['tests']})
        summary['controls'].append(entry)
        save(output / 'summary.json', summary)
        print(json.dumps(entry), flush=True)
        if result['infrastructure_status'] != 'ok' or result['submission_status'] != 'accepted':
            raise RuntimeError('Stop on infrastructure/submission failure: ' + name)
    assert all(json.loads(p.read_text())['removed'] for p in (output / 'workers').glob('worker-*/worker-receipt.json'))


if __name__ == '__main__':
    main()

"""No-model native acceptance probe; run its controller outside nested Seatbelt."""
import argparse
import json
from pathlib import Path
import shutil

from core import Package, save
from sandbox import NativeSandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--eval', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--codex', default=shutil.which('codex'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.absolute()
    args.output.mkdir(parents=True)
    result = {'status': 'infrastructure_failure', 'model_calls': 0}
    try:
        package = Package(args.eval, args.repo)
        result.update(package.provenance)
        result['synthetic_baseline_commit'] = package.prepare(args.output/'workspace')
        sandbox = NativeSandbox(args.codex, args.python, args.output/'controller')
        result['isolation'] = sandbox.canaries(args.output/'workspace', args.output/'boundary')
        result['environment'] = sandbox.environment(args.output/'workspace', args.output/'environment')
        result['resource_probe'] = sandbox.resource_probe(args.output/'workspace', args.output/'resources')
        result['limits'] = sandbox.features
        result['status'] = 'passed'
    except Exception as exc:
        result['error'] = type(exc).__name__+': '+str(exc)
        import traceback
        (args.output/'error.log').write_text(traceback.format_exc())
    save(args.output/'result.json', result)
    print(json.dumps(result, indent=2))
    return 0 if result['status']=='passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())

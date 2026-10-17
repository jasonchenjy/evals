"""Frozen instruction-only overlay; delegates all execution/grading to existing Pilot.

The trusted collector keeps the original synthetic baseline. Only the participant
Git baseline changes, because TASK.md must not retain A in reachable/dangling history.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
HARBOR = HERE.parents[1]
REPO = HARBOR.parent
sys.path.insert(0, str(HARBOR / 'pilot'))
import common
import run as pilot
from codex_agent import pilot_config

TEMPLATE = HARBOR / 'generated/pilot-live-fixed'
QUALIFICATION = HARBOR / 'raw/pilot-readiness-qualification-final'
OLD_PREFLIGHT = HARBOR / 'raw/pilot-readiness-environment-final'
IMAGE = 'sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12'
MODEL = 'openai/gpt-6.1-sol'
ORIGINAL_VALIDATE = common.validate_task
ORIGINAL_GATE = pilot.public_gate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def experiment_hashes():
    return {p.name:sha(p) for p in sorted(HERE.glob('*.py'))}


def load_lock():
    lock = json.loads((HERE / 'inputs.json').read_text())
    assert experiment_hashes() == lock['experiment_code_sha256'], 'Experiment code changed; redo packaging preflight'
    for name, digest in lock['instruction_files'].items():
        assert sha(HERE / name) == digest, 'Frozen instruction changed: ' + name
    assert common.adapter_hashes() == lock['adapter_hashes']
    assert common.task_hashes(TEMPLATE) == lock['qualified_template_hashes']
    old = json.loads((OLD_PREFLIGHT / 'summary.json').read_text())
    assert old['task_hashes'] == lock['qualified_template_hashes'] and old['adapter_hashes'] == lock['adapter_hashes']
    return lock


def validate_task(task, package):
    lock = load_lock()
    original = ORIGINAL_VALIDATE(TEMPLATE, package)  # Keep all original Eval/CLI/base checks.
    task = Path(task).resolve()
    variant = next((k for k in ('B', 'C') if task == (HERE / 'generated' / k).resolve()), None)
    assert variant, 'Only the two frozen experiment task paths are supported'
    expected = lock['variants'][variant]
    assert common.task_hashes(task) == expected['task_hashes'], 'Variant task changed'
    for name, digest in package.files.items():
        assert sha(task / 'environment/base' / name) == digest, name
    p = json.loads((task / 'provenance.json').read_text())
    for key in ('eval_id','eval_version','eval_lock_sha256','source_base_commit','baseline','image','codex_bundle_sha256'):
        assert p[key] == original[key], key
    assert p['instruction_sha256'] == expected['instruction_sha256'] == sha(task / 'instruction.md')
    assert (task / 'instruction.md').read_bytes() == (task / 'environment/base/TASK.md').read_bytes()
    assert p['experiment_variant'] == variant and p['agent_baseline'] == expected['agent_baseline']
    return p


async def public_gate(trial, provenance, canaries):
    # Original resource, public-payload, canary and network gates still run.
    await ORIGINAL_GATE(trial, dict(provenance, baseline=provenance['agent_baseline']), canaries)
    program = (HERE / 'inspect_visible.py').read_text()
    observed = await trial.agent_environment.exec('/usr/local/bin/python -I -c ' + shlex.quote(program), user='1000:1000')
    assert observed.return_code == 0, 'Filesystem inspection failed'
    inventory = json.loads(observed.stdout)
    variant = provenance['experiment_variant']
    lock = load_lock()
    expected = lock['variants'][variant]['public_files']
    assert inventory['work_public_files'] == expected
    assert inventory['base_public_files'] == expected
    for root in ('/work', '/base'):
        history = inventory['git'][root]
        assert history['head'] == provenance['agent_baseline'] and history['commit_count'] == 1
        assert not history['remotes'] and not history['unreachable_objects'] and not history['alternates']
        assert not history['gold_commit_present'] and not history['worktree_changes']
        assert history['all_objects'] == history['reachable_objects']
    # Whole-filesystem comparison to the clean task/image, plus known-private fingerprints.
    forbidden = set(lock['private_material_sha256'].values())
    assert not forbidden.intersection(x.get('sha256') for x in inventory['filesystem'].values())
    assert not inventory['forbidden_paths_found']
    assert not inventory['git_roots_other_than_base_work']
    assert inventory['instruction_a_present'] is False
    common.save(trial.paths.trial_dir / 'visible-inventory.json', inventory)


def install_overlay():
    pilot.validate_task = validate_task
    pilot.public_gate = public_gate


async def main(args):
    load_lock()
    args.output = args.output.resolve()
    assert args.output.is_relative_to(HERE / 'raw'), 'Experiment output must stay under its raw directory'
    task = HERE / 'generated' / args.variant
    install_overlay()
    if args.mode == 'preflight':
        import live_preflight
        live_preflight.validate_task = validate_task
        live_preflight.public_gate = public_gate
        await live_preflight.main(SimpleNamespace(task=task, output=args.output))
        summary = json.loads((args.output / 'summary.json').read_text())
        summary.update(experiment_variant=args.variant, experiment_code_sha256=experiment_hashes(),
                       experiment_inputs_sha256=sha(HERE / 'inputs.json'), filesystem_leakage_gate_passed=True)
        common.save(args.output / 'summary.json', summary)
    else:
        if not (args.auth_file and args.approve_container_credentials and args.approve_public_network):
            raise ValueError('Requires fresh human approval for this variant and selected credential before using flags')
        preflight = HERE / 'raw' / ('preflight-' + args.variant)
        summary = json.loads((preflight / 'summary.json').read_text())
        assert summary['experiment_code_sha256'] == experiment_hashes()
        assert summary['experiment_inputs_sha256'] == sha(HERE / 'inputs.json')
        assert summary['filesystem_leakage_gate_passed']
        comparison = json.loads((HERE / 'inventory-comparison.json').read_text())
        assert comparison['passed'] and comparison['inputs_sha256'] == sha(HERE / 'inputs.json')
        assert comparison['preflight_sha256'] == {k:sha(HERE / 'raw' / ('preflight-' + k) / 'summary.json') for k in ('B','C')}
        # Fixed configuration, exact inherited gates; no replacement Agent/Verifier or retry loop.
        await pilot.run(SimpleNamespace(task=task, output=args.output, repo=REPO.parent/'pytest',
            image=IMAGE, live=True, model=MODEL, auth_file=args.auth_file.resolve(),
            qualification=QUALIFICATION, security=HARBOR/'raw/pilot-security-final',
            worker_checks=HARBOR/'raw/pilot-worker-handoff', preflight=preflight,
            approve_container_credentials=True, approve_public_network=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'live'])
    parser.add_argument('--variant', choices=['B','C'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--auth-file', type=Path)
    parser.add_argument('--approve-container-credentials', action='store_true')
    parser.add_argument('--approve-public-network', action='store_true')
    args = parser.parse_args()
    os.environ.update(DOCKER_HOST='unix:///private/tmp/pytest5786-colima/default/docker.sock',
        DOCKER_CONFIG=str(HARBOR/'tools/docker'), HOME=str(HARBOR/'tools/home'), PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(main(args))

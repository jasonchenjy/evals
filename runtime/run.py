#!/usr/bin/env python3
"""Single pytest_5786 trial controller. All safety gates fail closed."""
import argparse
import datetime
import json
from pathlib import Path
import shutil

import agent
from core import InfrastructureError, Package, save
from sandbox import NativeSandbox
from submission import collect
from grading import grade


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval', required=True, type=Path)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--python', required=True, type=Path)
    parser.add_argument('--codex', default=shutil.which('codex'))
    parser.add_argument('--model', required=True)
    parser.add_argument('--client-home', type=Path, help='Optional dedicated runtime controller HOME already authenticated with supported Codex login; never the developer HOME')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--preflight-only', action='store_true', help='No model call; check boundaries/environment/context and report readiness')
    args = parser.parse_args(argv)
    out = args.output.absolute()
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error('Output directory must be new: '+str(out))
    result = {'schema_version': 1, 'trial_id': out.name, 'model': args.model, 'harness': 'codex',
              'status': 'not_executed', 'stage': 'verify', 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'agent_execution': {'status': 'not_executed', 'exit_code': None, 'timeout': False},
              'submission': {'status': 'not_executed', 'changed_files': []},
              'grading': {'infrastructure_status': 'not_executed', 'overall_resolved': None, 'dimensions': {}},
              'artifacts': {}, 'model_calls': 0}
    package = None
    def stage(name):
        result['stage'] = name
        save(out/'result.json', result)
        print('stage='+name, flush=True)
    try:
        package = Package(args.eval, args.repo)
        result.update(package.provenance)
        stage('prepare')
        workspace = out/'agent/workspace'
        baseline = package.prepare(workspace)
        result['synthetic_baseline_commit'] = baseline
        save(out/'controller/baseline.json', {'synthetic_baseline_commit': baseline})
        sandbox = NativeSandbox(args.codex, args.python, out/'controller')
        result['harness_identity'] = sandbox.identity
        result['harness_version'] = sandbox.identity['version']
        result['resource_controls'] = sandbox.features
        stage('isolation')
        sandbox.canaries(workspace, out/'agent-boundary')
        # A separate domain receives separate scratch and cannot see the agent workspace.
        grading_workspace = out/'grading-boundary/workspace'
        package.prepare(grading_workspace)
        sandbox.canaries(grading_workspace, out/'grading-boundary/probe')
        stage('environment')
        result['environment'] = sandbox.environment(workspace, out/'environment')
        result['resource_probe'] = sandbox.resource_probe(workspace, out/'resources')
        stage('agent_contract')
        inspection = agent.inspect(sandbox, workspace, out/'agent-contract', args.client_home)
        result['harness_version'] = inspection['version']
        result['agent_readiness'] = inspection
        result['artifacts']['agent_inspection'] = str(out/'agent-contract/inspection.json')
        if args.preflight_only:
            result['status'] = 'not_executed'
            result['readiness'] = 'PARTIALLY_READY'
            result['blockers'] = inspection['blockers'] + [
                'Aggregate RAM/PID/disk and detached-descendant containment are not established']
            return 2 if result['blockers'] else 0
        stage('agent')
        execution = agent.execute(sandbox, workspace, out/'agent-execution', args.model,
                                  package.task['budgets']['trial_wall_seconds'], inspection)
        result['model_calls'] = 1
        result['agent_execution'] = dict(execution, status='timeout' if execution['timeout'] else 'completed',
                                          exit_code=execution['returncode'])
        if execution['timeout']:
            result['status'] = 'agent_timeout'
            return 1
        if execution['returncode']!=0 or execution['output_limit_exceeded']:
            raise InfrastructureError('Codex invocation did not complete successfully')
        stage('collect')
        result['submission'] = collect(package, workspace, baseline, out/'submission')
        stage('grade')
        graded = grade(package, sandbox, result['submission']['patch'], out/'grading', result['submission']['source_sha256'])
        result['grading'] = graded
        result['artifacts']['grader_result'] = str(out/'grading/result.json')
        if graded['infrastructure_status']!='ok':
            raise InfrastructureError(graded.get('error','Grading infrastructure failed'))
        result['status'] = 'invalid_submission' if graded['submission_status']=='rejected' else ('resolved' if graded['overall_resolved'] else 'unresolved')
        result['readiness'] = 'READY'
    except Exception as exc:
        if package is not None and isinstance(exc, package.grader.RejectedPatch):
            result['status'] = 'invalid_submission'
            result['submission']['status'] = 'rejected'
        else:
            result['status'] = 'infrastructure_failure'
            result['infrastructure_status'] = 'error'
            if result['stage'] == 'grade':
                result['grading']['infrastructure_status'] = 'error'
        result['error'] = type(exc).__name__+': '+str(exc)
        result['readiness'] = 'PARTIALLY_READY'
    finally:
        result['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(out/'result.json', result)
        (out/'summary.md').write_text('# '+result['trial_id']+'\n\nStatus: '+result['status']+'\n\nModel: '+args.model+'\n\nOverall resolved: '+str(result['grading']['overall_resolved'])+'\n\n'+result.get('error','')+'\n')
        print(json.dumps({'status':result['status'],'overall_resolved':result['grading']['overall_resolved'],
                          'result':str(out/'result.json'),'error':result.get('error')}))
    return 0 if result['status']=='resolved' else (2 if result['status']=='infrastructure_failure' else 1)


if __name__=='__main__':
    raise SystemExit(main())

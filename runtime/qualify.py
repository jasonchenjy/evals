"""Seven existing trusted controls through the native grader adapter; no models."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from core import Package, save, bounded
from sandbox import NativeSandbox
from grading import grade
from submission import assert_applied

CONTROLS=['noop','historical','complete','alternative','last_only','testreport_only','text_only']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval',required=True,type=Path)
    parser.add_argument('--repo',required=True,type=Path)
    parser.add_argument('--python',required=True,type=Path)
    parser.add_argument('--codex',default=shutil.which('codex'))
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    out=args.output.absolute();out.mkdir(parents=True)
    summary={'model_calls':0,'scope':'trusted fixed controls through isolated candidate workers','controls':[],'qualification_passed':False}
    try:
        package=Package(args.eval,args.repo);summary.update(package.provenance)
        sandbox=NativeSandbox(args.codex,args.python,out/'controller')
        summary['harness_identity'] = sandbox.identity
        workspace=out/'agent-workspace';package.prepare(workspace)
        summary['agent_boundary']=sandbox.canaries(workspace,out/'agent-boundary')
        summary['environment']=sandbox.environment(workspace,out/'environment')
        for name in CONTROLS:
            patch=package.root/'private/oracle'/(name+'.patch')
            # Expected applied bytes derived by independent controller-side patch application.
            # No Oracle file is readable in any worker; patches never enter agent-workspace.
            expected_dir=out/'controller'/('expected-'+name)
            package.prepare(expected_dir)
            expected=assert_applied(package,patch,expected_dir)
            result=grade(package,sandbox,patch,out/name,expected)
            checks={x['id']:x['status'] for x in result['tests']}
            entry={'control':name,'infrastructure_status':result['infrastructure_status'],
                   'overall_resolved':result['overall_resolved'],'checks':checks,
                   'result':str(out/name/'result.json'),
                   'expected_overall':name in ['complete','alternative']}
            entry['expectation_met']=entry['infrastructure_status']=='ok' and entry['overall_resolved']==entry['expected_overall']
            summary['controls'].append(entry);save(out/'summary.json',summary)
            print(name,entry['infrastructure_status'],entry['overall_resolved'],checks,flush=True)
            if result['infrastructure_status']!='ok':
                raise RuntimeError('Infrastructure gate failed for '+name+': '+result.get('error',''))
        by={x['control']:x for x in summary['controls']}
        summary['boundary_checks']={
            'noop_original_fails':by['noop']['checks']['A01']=='failed',
            'noop_unaffected_passes':all(by['noop']['checks'][x]=='passed' for x in ['D01','D02']),
            'historical_original_passes':all(by['historical']['checks'][x]=='passed' for x in ['A01','A02']),
            'historical_focused_passes':by['historical']['checks']['H01']=='passed',
            'historical_regression_exposed':all(by['historical']['checks'][x]=='error' for x in ['C03','D03']),
            'last_only_rejected':by['last_only']['checks']['A01']=='failed',
            'testreport_only_collect_rejected':by['testreport_only']['checks']['B01']=='failed',
            'text_only_structure_rejected':by['text_only']['checks']['B02']=='error',
            'alternative_H02_preserved':by['alternative']['checks']['H02']=='failed'}
        contract=bounded([sys.executable,'-B',str(package.root/'private/qualification/test_grader_contract.py')],
                          package.root,{'PATH':'/opt/homebrew/bin:/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},30,out/'grader-contract')
        summary['original_grader_contract']=contract
        summary['qualification_passed']=all(x['expectation_met'] for x in summary['controls']) and all(summary['boundary_checks'].values()) and contract['returncode']==0
    except Exception as exc:
        summary['error']=type(exc).__name__+': '+str(exc)
        import traceback
        (out/'error.log').write_text(traceback.format_exc())
        print(summary['error'],flush=True)
    save(out/'summary.json',summary)
    return 0 if summary['qualification_passed'] else 2


if __name__=='__main__':raise SystemExit(main())

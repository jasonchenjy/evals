"""Publish selected pilot evidence locally; refuse suspected credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def curate(source, target):
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    names = {'summary.json','agent-probes.json','results.json','agent-gate.json',
             'docker-inspect.json','effective-policy.json','handoff.json','cleanup.json',
             'boundary.json','resource_results.json','runtime_execution.json',
             'submission.patch','submission.json','result.json','reward.json','config.json',
             'lock.json','trial.log','exception.txt','trajectory.json','codex.txt',
             'public-preflight.txt','initial-environment.txt','control.txt',
             'authorization-scope.json','attempt-audit.json','expected-rejection.json','probe-execution.json'}
    names.update({'tool-preflight.json','roundtrip.json','offline-fixture.json','focused-tests.txt',
                  'home-usage.json','initial-verifier.json','diagnostic.json','process-check.json','hidden-tests.txt'})
    for p in sorted(source.rglob('*')):
        if not p.is_file() or p.is_symlink(): continue
        rel = p.relative_to(source)
        if any(x in rel.parts for x in ['workspace','base','captured','mirror','images','artifacts','independent-apply']): continue
        if any(x.endswith('-worker-scratch') or x.endswith('-worker-inputs') for x in rel.parts): continue
        allowed = p.name in names or p.name.endswith('-receipt.json')
        allowed |= ('grader' in rel.parts and p.name in {'worker.log','observation.json','preflight.log','controller.stdout'})
        allowed |= ('sessions' in rel.parts and p.suffix == '.jsonl')
        if not allowed: continue
        if p.stat().st_size > 32*1024*1024: raise ValueError('Evidence file too large')
        raw = p.read_bytes(); text = raw.decode('utf-8')
        patterns = [r'"(?:access_token|refresh_token|id_token)"\s*:\s*"[^" ]{10,}"',
                    r'\bsk-[A-Za-z0-9_-]{20,}', r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}']
        if any(re.search(pattern,text) for pattern in patterns):
            raise ValueError('Potential credential; evidence not publishable: '+str(rel))
        out = target/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
        entries.append(dict(path=str(rel),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    (target/'evidence-manifest.json').write_text(json.dumps(entries,indent=2)+'\n')
    print(str(target),len(entries),'files, credential-pattern scan passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('--name',required=True)
    a=parser.parse_args()
    if not re.fullmatch('[a-zA-Z0-9_-]+',a.name): raise ValueError('Invalid evidence name')
    curate(a.source,ROOT/'evidence'/a.name)

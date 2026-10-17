"""Clone the qualified public task, replace only instruction metadata, rebuild Git."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from experiment import HERE, HARBOR, REPO, TEMPLATE, OLD_PREFLIGHT, common, experiment_hashes, sha


def main():
    package = common.load_runtime()[0](REPO/'pytest_5786', REPO.parent/'pytest')
    original = common.validate_task(TEMPLATE, package)
    old = json.loads((OLD_PREFLIGHT/'summary.json').read_text())
    assert common.task_hashes(TEMPLATE) == old['task_hashes']
    assert common.adapter_hashes() == old['adapter_hashes']
    lock = dict(schema_version=1, model='openai/gpt-6.1-sol', agent_timeout_seconds=1800,
        experiment_code_sha256=experiment_hashes(), adapter_hashes=common.adapter_hashes(),
        eval_lock_sha256=sha(REPO/'pytest_5786/checksums.json'),
        instruction_files={n:sha(HERE/n) for n in ['variant_a.md','variant_b.md','variant_c.md','operational_appendix.md','original_issue.json']},
        qualified_template_hashes=old['task_hashes'], variants={})
    paths = [REPO/'pytest_5786/private/grader.py', REPO/'pytest_5786/private/tests/behavior.py']
    paths += list((REPO/'pytest_5786/private/oracle').glob('*.patch'))
    paths += list((REPO/'pytest_5786/iteration').glob('*.md'))
    paths += list((REPO/'pytest_5786/iteration/controls').glob('*.patch'))
    paths += [HARBOR/'evidence/pytest5786-stage3-20261017T075426Z/codex/submission/submission.patch',
              HARBOR/'evidence/pytest5786-stage3-20261017T075426Z/codex/agent/trajectory.json',
              HARBOR/'evidence/first-real-pilot-analysis.md', REPO/'pytest_5786/instruction.md']
    lock['private_material_sha256'] = {str(p.relative_to(REPO)):sha(p) for p in paths if p.stat().st_size>100}
    for variant in ('B','C'):
        task = HERE/'generated'/variant
        shutil.copytree(TEMPLATE, task)
        prompt = (HERE/f'variant_{variant.lower()}.md').read_text().rstrip()+'\n\n'+(HERE/'operational_appendix.md').read_text()
        (task/'instruction.md').write_text(prompt)
        base = task/'environment/base'
        (base/'TASK.md').write_text(prompt)
        metadata = json.loads((base/'eval_public.json').read_text())
        del metadata['capability']
        (base/'eval_public.json').write_text(json.dumps(metadata,indent=2)+'\n')
        # Newly copied generated Git only; no original repository/history is touched.
        shutil.rmtree(base/'.git')
        env = dict(os.environ,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,
            GIT_AUTHOR_DATE='2019-08-30T00:00:00+00:00',GIT_COMMITTER_DATE='2019-08-30T00:00:00+00:00')
        for args in [['init','-q'],['add','.'],['-c','user.name=Eval Baseline','-c','user.email=eval@invalid',
                     '-c','commit.gpgsign=false','commit','-qm','Evaluation baseline']]:
            subprocess.run(['git','-c','init.templateDir=','-c','core.hooksPath='+os.devnull,
                '-c','core.autocrlf=false','-C',str(base),*args],check=True,env=env)
        head = subprocess.check_output(['git','-C',str(base),'rev-parse','HEAD'],text=True).strip()
        p = dict(original, instruction_sha256=sha(task/'instruction.md'),
            experiment_variant=variant, agent_baseline=head,
            original_instruction_sha256=original['instruction_sha256'],
            operational_appendix_sha256=sha(HERE/'operational_appendix.md'))
        common.save(task/'provenance.json',p)
        public = {str(p.relative_to(base)):sha(p) for p in base.rglob('*') if p.is_file() and '.git' not in p.relative_to(base).parts}
        assert public.keys() == {str(p.relative_to(TEMPLATE/'environment/base')) for p in (TEMPLATE/'environment/base').rglob('*') if p.is_file() and '.git' not in p.relative_to(TEMPLATE/'environment/base').parts}
        changes = {p for p in public if public[p] != sha(TEMPLATE/'environment/base'/p)}
        assert changes == {'TASK.md','eval_public.json'}
        # Every non-prompt/Git artifact must still equal the qualified template.
        actual = common.task_hashes(task)
        changed = {p for p in set(actual)|set(old['task_hashes']) if actual.get(p)!=old['task_hashes'].get(p)}
        assert all(p in {'instruction.md','provenance.json','environment/base/TASK.md','environment/base/eval_public.json'} or p.startswith('environment/base/.git/') for p in changed)
        lock['variants'][variant] = dict(instruction_sha256=sha(task/'instruction.md'), agent_baseline=head,
            public_files=public, task_hashes=actual, changed_task_paths=sorted(changed),
            task_manifest_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest())
    assert {k for k in lock['variants']['B']['public_files'] if lock['variants']['B']['public_files'][k]!=lock['variants']['C']['public_files'][k]} == {'TASK.md'}
    common.save(HERE/'inputs.json',lock)
    print('Frozen B/C inputs; original source and verifier unchanged.')


if __name__=='__main__':
    main()

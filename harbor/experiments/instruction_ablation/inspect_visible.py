"""Runs inside the actual participant container before tools/authentication.

Read every accessible regular file on persistent filesystems; record symlinks,
permissions failures and excluded virtual filesystems explicitly. No secrets loaded.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def git(root, *args):
    return subprocess.check_output(['git','-c','safe.directory='+root,'-C',root,*args], text=True, stderr=subprocess.DEVNULL).strip()


os.environ['GIT_OPTIONAL_LOCKS'] = '0'
files = {}
errors = []
for root, dirs, names in os.walk('/', followlinks=False, onerror=lambda e: errors.append({'path':e.filename,'errno':e.errno})):
    if root == '/':
        dirs[:] = [d for d in dirs if d not in ('proc','sys','dev')]
    for name in dirs[:] + names:
        p = Path(root) / name
        try:
            mode = p.lstat().st_mode
            if stat.S_ISLNK(mode):
                files[str(p)] = {'symlink':os.readlink(p)}
            elif stat.S_ISREG(mode):
                files[str(p)] = {'bytes':p.stat().st_size, 'sha256':digest(p)}
            elif not stat.S_ISDIR(mode):
                files[str(p)] = {'special_file':stat.S_IFMT(mode)}
        except OSError as e:
            errors.append({'path':str(p),'errno':e.errno})

histories = {}
for root in ('/work','/base'):
    all_objects = sorted(git(root,'cat-file','--batch-all-objects','--batch-check=%(objectname)').splitlines())
    reachable = sorted(set(x.split()[0] for x in git(root,'rev-list','--objects','--all').splitlines()))
    gold = subprocess.run(['git','-c','safe.directory='+root,'-C',root,'cat-file','-e','01082fea12649384aab44306f49503de1374c4a1^{commit}'], stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0
    histories[root] = dict(head=git(root,'rev-parse','HEAD'), commit_count=int(git(root,'rev-list','--all','--count')),
        remotes=git(root,'remote'), worktree_changes=git(root,'status','--porcelain'),
        all_objects=all_objects, reachable_objects=reachable,
        unreachable_objects=git(root,'fsck','--full','--no-reflogs','--unreachable'),
        alternates=Path(root+'/.git/objects/info/alternates').exists(), gold_commit_present=gold)

def public(root):
    return {p[len(root)+1:]:v['sha256'] for p,v in files.items()
            if p.startswith(root+'/') and '/.git/' not in p and 'sha256' in v}

forbidden = ('pytest_5786/iteration', 'pytest_5786/private', '/harbor/evidence/', '/harbor/experiments/',
             '/private/oracle/', '/submission.patch', '/trajectory.json', '/grader.py')
roots = sorted(p.rsplit('/.git/',1)[0] for p in files if p.endswith('/.git/HEAD'))
# A-specific paragraph should be absent in all text-bearing task/source exports.
a_present = False
for root in ('/work','/base'):
    for p in Path(root).rglob('TASK.md'):
        if 'including failures during test collection, captured output and attached report sections' in p.read_text():
            a_present = True
print(json.dumps(dict(filesystem=files, unreadable=errors,
    virtual_filesystems_excluded=['/proc','/sys','/dev'],
    work_public_files=public('/work'), base_public_files=public('/base'), git=histories,
    git_roots_other_than_base_work=[x for x in roots if x not in ('/work','/base')],
    forbidden_paths_found=[p for p in files if any(x in p for x in forbidden)], instruction_a_present=a_present)))

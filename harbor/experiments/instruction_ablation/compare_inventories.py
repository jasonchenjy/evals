"""Compare actual container files, allowing only prompts, derived Git and Docker identity."""
import hashlib
import json
from experiment import HERE, common, load_lock, sha


def main():
    lock = load_lock()
    observations = {k:json.loads((HERE/'raw'/('preflight-'+k)/'visible-inventory.json').read_text()) for k in ('B','C')}
    a,b = (observations[k]['filesystem'] for k in ('B','C'))
    differences = sorted(p for p in set(a)|set(b) if a.get(p)!=b.get(p))
    # Docker-generated hosts/hostname files are not experimental payload.
    docker_identity = {'/etc/hosts','/etc/hostname','/etc/resolv.conf'}
    prompt_files = {'/work/TASK.md','/base/TASK.md'}
    unexpected = [p for p in differences if p not in docker_identity|prompt_files and not p.startswith(('/work/.git/','/base/.git/'))]
    assert not unexpected, unexpected
    assert observations['B']['work_public_files'].keys()==observations['C']['work_public_files'].keys()
    assert {k for k,v in observations['B']['work_public_files'].items() if v!=observations['C']['work_public_files'][k]}=={'TASK.md'}
    result = dict(passed=True,inputs_sha256=sha(HERE/'inputs.json'),
        preflight_sha256={k:sha(HERE/'raw'/('preflight-'+k)/'summary.json') for k in ('B','C')},
        actual_filesystem_inventory_sha256={k:sha(HERE/'raw'/('preflight-'+k)/'visible-inventory.json') for k in ('B','C')},
        filesystem_entries={k:len(observations[k]['filesystem']) for k in ('B','C')},
        public_file_count=len(observations['B']['work_public_files']), differences=differences,
        unexpected_differences=unexpected,normalized_exceptions=['prompt copies','Git objects/index/logs derived from prompt','Docker hosts/hostname/resolv metadata'],
        git_object_audit='Each actual Git store contains exactly one commit and only its reachable objects; no remotes/alternates/gold commit.',
        scope='All accessible persistent regular files hashed; symlinks and unreadable paths recorded; virtual /proc,/sys,/dev excluded. No claim about public Internet or model training exposure.')
    common.save(HERE/'inventory-comparison.json',result)
    print(json.dumps({k:result[k] for k in ['passed','filesystem_entries','public_file_count','unexpected_differences']}))


if __name__=='__main__':
    main()

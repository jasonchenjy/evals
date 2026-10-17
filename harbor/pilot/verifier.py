"""Harbor BaseVerifier interface; original scorer stays on trusted controller."""
import asyncio
import json
import os
from pathlib import Path

from harbor.verifier.base import BaseVerifier
from harbor.models.verifier.result import VerifierResult
from common import REPO, load_runtime, save


class IsolatedVerifier(BaseVerifier):
    def __init__(self, *, repo, image, **kwargs):
        super().__init__(**kwargs)
        self.repo, self.image = Path(repo), image

    async def verify(self):
        return await asyncio.to_thread(self.grade)

    def grade(self):
        Package, ContainerSandbox, grade, _, assert_applied = load_runtime()
        package = Package(REPO / 'pytest_5786', self.repo)
        trial = self.trial_paths.trial_dir
        submission = json.loads((trial / 'submission/submission.json').read_text())
        patch = trial / 'submission/submission.patch'
        fresh = trial / 'independent-apply'
        package.prepare(fresh)
        assert_applied(package, patch, fresh, submission['source_sha256'])
        # Confirm the entire allowed source inventory, including unchanged files.
        frozen = json.loads((trial / 'agent-environment/handoff.json').read_text())['source']
        import hashlib
        applied = {str(p.relative_to(fresh)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (fresh / 'src').rglob('*.py')}
        assert applied == {n: v['sha256'] for n, v in frozen.items()}
        sandbox = ContainerSandbox('/usr/local/bin/docker', os.environ['DOCKER_HOST'],
                                   os.environ['DOCKER_CONFIG'], self.image, trial / 'workers')
        sandbox.base.env['DOCKER_BUILDKIT'] = '0'  # Reused worker builder consumes an immutable local image ID.
        result = grade(package, sandbox, patch, self.trial_paths.verifier_dir / 'grader',
                       submission['source_sha256'])
        if result['infrastructure_status'] != 'ok' or result['submission_status'] != 'accepted':
            raise RuntimeError('Independent grader failed: ' + result.get('error', 'invalid result'))
        load_runtime()  # Detect concurrent changes to the reused implementation.
        reward = {'reward': float(result['overall_resolved'])}
        reward.update({k: float(v['satisfied']) for k, v in result['dimensions'].items()})
        save(self.trial_paths.verifier_dir / 'reward.json', reward)
        save(self.trial_paths.verifier_dir / 'boundary.json', dict(
            trusted_scoring='host; original grade() with every candidate Python call intercepted',
            candidate_execution='fresh nonroot read-only network-none worker per check',
            oracle_in_worker=False, credentials_in_worker=False,
            entire_source_bytes_match=True, host_scoring_result_unmounted=True,
            limitation='Candidate and behavioral check share an interpreter; not a production anti-cheating proof'))
        return VerifierResult(rewards=reward)

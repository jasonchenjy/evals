"""Image-owned bootstrap. Candidate code runs only after the container policy exists.

This does not claim resistance to candidate interference with its check interpreter.
No path received from a candidate is ever opened on the controller host.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, '/opt/pytest5786-worker')
from core import bounded, InfrastructureError
from handoff import Directory, OBSERVATION_LIMIT, read_bytes


def main():
    request = json.load(sys.stdin)  # controller-owned input, not a participant tool
    shutil.copytree('/inputs/workspace', '/trial/workspace')
    scratch = Path('/trial/scratch')
    for name in ['home', 'tmp']:
        (scratch/name).mkdir(parents=True)
    result = {'schema_version': 1, 'handoff_status': 'rejected'}
    try:
        with Directory(scratch) as submitted:
            execution = bounded(request['command'], '/trial/workspace', request['env'],
                                request['timeout'], '/trial/capture/process', output_limit=8*1024*1024)
            result['execution'] = execution
            if execution.get('launch_error') or execution.get('cleanup_error') or execution.get('descendant_pipe_leak') or execution['output_limit_exceeded']:
                raise InfrastructureError('Worker execution or capture failed')
            result['stdout'] = base64.b64encode(read_bytes(execution['stdout'])).decode('ascii')
            result['stderr'] = base64.b64encode(read_bytes(execution['stderr'])).decode('ascii')
            raw = submitted.read('observation.json', OBSERVATION_LIMIT, missing_ok=True)
            result['observation'] = None if raw is None else base64.b64encode(raw).decode('ascii')
            result['handoff_status'] = 'accepted'
    except InfrastructureError:
        # Do not include rejected file contents or arbitrary exception text.
        result = {'schema_version': 1, 'handoff_status': 'rejected',
                  'reason': 'Unsafe, replaced, oversized or inaccessible worker output'}
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()

import os
assert os.environ.get('PYTEST_XDIST_WORKER') == 'gw0'
class RemoteProblem(Exception):
    pass

def trigger():
    try:
        raise ValueError('source-side-cause-607')
    except ValueError as cause:
        raise RuntimeError('consumer-side-failure-613') from cause

def test_failure():
    print('capture-619')
    trigger()

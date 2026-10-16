import os
assert os.environ.get('PYTEST_XDIST_WORKER') == None
class RemoteProblem(Exception):
    pass

def trigger():
    try:
        raise ValueError('source-side-cause-607')
    except ValueError as cause:
        raise RuntimeError('consumer-side-failure-613')

def test_failure():
    print('capture-619')
    trigger()

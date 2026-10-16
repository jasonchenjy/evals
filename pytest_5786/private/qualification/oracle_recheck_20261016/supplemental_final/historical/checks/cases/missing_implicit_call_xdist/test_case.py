import os
assert os.environ.get('PYTEST_XDIST_WORKER') == 'gw0'
class RemoteProblem(Exception):
    pass

def trigger():
    error = RuntimeError('consumer-side-failure-613')
    error.__context__ = RemoteProblem('source-side-cause-607')
    raise error

def test_failure():
    print('capture-619')
    trigger()

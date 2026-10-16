import os
assert os.environ.get('PYTEST_XDIST_WORKER') == None
class RemoteProblem(Exception):
    pass

def trigger():
    error = RuntimeError('consumer-side-failure-613')
    error.__cause__ = RemoteProblem('source-side-cause-607')
    raise error

trigger()

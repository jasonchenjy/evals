"""Reuse the existing ten-case worker handoff probe without editing Runtime."""
import argparse
import os
from pathlib import Path
import sys

from common import ROOT, REPO, load_runtime


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',required=True)
    p.add_argument('--endpoint',default='unix:///private/tmp/pytest5786-colima/default/docker.sock')
    a=p.parse_args()
    load_runtime()
    import probe_container_handoff as probe
    original=probe.ContainerSandbox
    class Sandbox(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.base.env['DOCKER_BUILDKIT']='0'
    probe.ContainerSandbox=Sandbox
    sys.argv=['worker-checks','--eval',str(REPO/'pytest_5786'),'--repo',str(REPO.parent/'pytest'),
              '--image',a.image,'--endpoint',a.endpoint,'--client-config',str(ROOT/'tools/docker'),
              '--output',str(a.output.resolve())]
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    probe.main()

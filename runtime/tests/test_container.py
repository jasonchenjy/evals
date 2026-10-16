"""Policy/transport regressions; actual isolation is tested by probe_container*.py."""
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import InfrastructureError
from container_boundary import create_command, validate_inspection, MIB
from container_sandbox import decode_envelope, snapshot_files
from probe_cli_inventory import request_inventory

IMAGE = 'sha256:'+'a'*64
NAME = 'pytest5786-'+'b'*24


class ContainerTests(unittest.TestCase):
    def test_explicit_bounded_policy(self):
        command = create_command('/docker','unix:///owned.sock','/own-config',NAME,IMAGE,'pass')
        for flag in ('--read-only','--init','--interactive'):
            self.assertIn(flag,command)
        for flag,value in [('--network','none'),('--cap-drop','ALL'),('--user','1000:1000'),
                           ('--memory',str(4096*MIB)),('--memory-swap',str(4096*MIB)),
                           ('--pids-limit','128'),('--cpus','2'),('--log-driver','none')]:
            self.assertEqual(command[command.index(flag)+1],value)
        self.assertFalse(set(command)&{'--volume','-v','--privileged','--publish','-p'})

    def test_reject_mutable_image_remote_daemon_and_large_limits(self):
        for kwargs in ({'image':'python:latest'}, {'endpoint':'tcp://remote:2375'},
                       {'memory_mib':4097},{'pids':129},{'disk_mib':2049},{'name':'someone-else'}):
            args=dict(docker='/docker',endpoint='unix:///owned.sock',client_config='/cfg',name=NAME,image=IMAGE,script='pass')
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(InfrastructureError): create_command(**args)

    def test_effective_policy_must_match_before_start(self):
        info={'Image':IMAGE,'Config':{'User':'1000:1000','Labels':{'pytest5786.owner':NAME}},'Mounts':[],
              'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'Privileged':False,
              'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'Memory':4096*MIB,
              'MemorySwap':4096*MIB,'PidsLimit':128,'NanoCpus':2000000000,'ShmSize':MIB,
              'Init':True,'Tmpfs':{'/trial':'rw,nosuid,nodev,size='+str(2047*MIB)+',mode=700,uid=1000,gid=1000'},
              'LogConfig':{'Type':'none'},'IpcMode':'private'}}
        validate_inspection(info,NAME,IMAGE)
        for key,value in [('NetworkMode','bridge'),('Memory',0),('PidsLimit',0),('Binds',['/home:/home']),
                          ('Privileged',True),('PidMode','host'),('ReadonlyRootfs',False),('CapAdd',['SYS_ADMIN'])]:
            bad=copy.deepcopy(info);bad['HostConfig'][key]=value
            with self.subTest(key=key),self.assertRaises(InfrastructureError): validate_inspection(bad,NAME,IMAGE)

    def test_transport_normal_and_rejected_payloads(self):
        payload={'schema_version':1,'handoff_status':'accepted','execution':{'returncode':0,'timeout':False},
                 'stdout':base64.b64encode(b'normal log').decode(),'stderr':'','observation':None}
        self.assertEqual(decode_envelope(json.dumps(payload))[1]['stdout'],b'normal log')
        for raw in (b'not json',json.dumps(dict(payload,handoff_status='rejected',reason='FAKE_SECRET')).encode(),
                    json.dumps(dict(payload,stdout='@badbase64')).encode(),
                    json.dumps(dict(payload,observation=base64.b64encode(b'x'*(1024*1024+1)).decode())).encode()):
            with self.assertRaises(InfrastructureError) as caught: decode_envelope(raw)
            self.assertNotIn('FAKE_SECRET',str(caught.exception))

    def test_image_context_rejects_links_and_fifo(self):
        import os
        for kind in ('link','fifo'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);p=root/'entry'
                if kind=='link':p.symlink_to('/etc/hosts')
                else:os.mkfifo(p)
                with self.assertRaises(InfrastructureError):snapshot_files(root)

    def test_wire_inventory_in_additional_tools_is_not_empty(self):
        wire={'input':[{'type':'additional_tools','tools':[{'type':'namespace','name':'collaboration',
              'tools':[{'type':'function','name':'spawn_agent'}]}]}]}
        found=request_inventory(wire)
        self.assertEqual(found['direct_tools'],['collaboration.spawn_agent'])
        self.assertEqual(found['prohibited_or_unnecessary_tools'],['collaboration.spawn_agent'])
        self.assertFalse(found['complete_dynamic_inventory_verified'])

    def test_historical_build_pins_match_eval(self):
        root=Path(__file__).resolve().parents[2]
        self.assertEqual((root/'runtime/container/requirements.txt').read_bytes(),
                         (root/'pytest_5786/requirements.txt').read_bytes())

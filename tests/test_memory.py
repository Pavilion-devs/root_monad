import copy
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from memory import Memory,ZERO
from protocol import digest,sign
ROOT=Path(__file__).resolve().parents[1]
V=json.loads((ROOT/'fixtures/authority-vector.json').read_text())

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='portable-memory-unit-')
        self.path=Path(self.tmp.name)/'memory.sqlite'; self.key=os.urandom(32)
        self.config={'projectId':V['control']['projectId'],'owner':V['owner'],'domain':V['domain']}
        snap={'formatVersion':'0','projectId':self.config['projectId'],'previousDigest':ZERO,'records':[],'sources':[],'currentIds':[],'resolutions':[]}
        c={**copy.deepcopy(V['control']),'snapshotDigest':digest('snapshot',snap)}
        cp={**V['checkpoint'],'controlDigest':digest('control',c)}
        self.genesis={'control':c,'snapshot':snap,'checkpoint':cp,'signature':sign(V['testOwnerKey'],V['domain'],'Checkpoint',cp)}
        self.m=Memory(self.path,self.key,self.config,self.genesis)
    def tearDown(self): self.m.close();self.tmp.cleanup()
    def wire(self,op,payload,key=None,nonce=None):
        c=self.m.current()['control']; now=int(time.time())
        body={'formatVersion':'0','projectId':c['projectId'],'method':'POST','path':f"/v0/projects/{c['projectId']}/{op}",'operation':op,'payload':payload}
        auth={'projectId':c['projectId'],'serviceId':c['serviceId'],'checkpointDigest':digest('control',c),'requestDigest':digest('request',body),'nonce':nonce or '0x'+os.urandom(32).hex(),'deadline':str(now+120)}
        return {'auth':auth,'body':body,'signature':sign(key or V['testAppKey'],V['domain'],'Request',auth)}
    def proposal(self):
        project=self.config['projectId']; sid='0x'+os.urandom(32).hex()
        return {'formatVersion':'0','projectId':project,'id':'0x'+os.urandom(32).hex(),'author':V['app'], 'baseCheckpoint':self.m.current()['checkpoint']['controlDigest'],
                'sources':[{'formatVersion':'0','projectId':project,'id':sid,'kind':'application_observation','speaker':'Test app','excerpt':'Evidence fixture','locator':None,'occurredAt':None}],
                'records':[{'formatVersion':'0','projectId':project,'id':'0x'+os.urandom(32).hex(),'kind':'decision','content':'Sensitive fixture alpha 79432','author':V['app'],'sourceIds':[sid],'replaces':None}],'retractIds':[]}
    def approve(self,payload):
        review=self.m.execute(self.wire('prepare',payload,V['testOwnerKey']))
        cp=review['checkpoint']; sig=sign(V['testOwnerKey'],V['domain'],'Checkpoint',cp)
        return self.m.execute(self.wire('commit',{'checkpoint':cp,'signature':sig},V['testOwnerKey']))
    def test_failed_proposal_rolls_back_sources_and_nonce(self):
        p=self.proposal();p['records'][0]['sourceIds']=['0x'+'aa'*32]
        before=self.m.db.execute('SELECT count(*) FROM objects').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'MISSING_SOURCE'): self.m.execute(self.wire('proposals',p))
        self.assertEqual(self.m.db.execute('SELECT count(*) FROM objects').fetchone()[0],before)
        self.assertEqual(self.m.db.execute('SELECT count(*) FROM receipts').fetchone()[0],0)
    def test_id_reuse_self_cycle_and_missing_targets(self):
        p=self.proposal();self.m.execute(self.wire('proposals',p))
        reused=copy.deepcopy(p);reused['id']='0x'+'ab'*32;reused['records'][0]['content']='Changed body same ID'
        with self.assertRaisesRegex(ValueError,'ID_CONFLICT'): self.m.execute(self.wire('proposals',reused))
        for target in ['self','missing']:
            q=self.proposal();q['records'][0]['replaces']=q['records'][0]['id'] if target=='self' else '0x'+'bb'*32
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'INVALID_TRANSITION'):
                self.m.execute(self.wire('proposals',q))
    def test_proposal_retry_after_restart_and_nonce_mismatch(self):
        p=self.proposal();wire=self.wire('proposals',p);first=self.m.execute(wire)
        self.m.close();self.m=Memory(self.path,self.key,self.config)
        self.assertEqual(self.m.execute(wire),first)
        self.assertEqual(self.m.db.execute('SELECT count(*) FROM inbox').fetchone()[0],1)
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):
            self.m.execute(self.wire('context',{},nonce=wire['auth']['nonce']))
    def test_revocation_blocks_cached_read_and_new_request(self):
        wire=self.wire('context',{});self.m.execute(wire)
        self.approve({'accept':[],'reject':[],'grants':[]})
        for request in [wire,self.wire('context',{})]:
            with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'): self.m.execute(request)
    def test_wrong_key_and_ciphertext_tampering(self):
        with self.assertRaisesRegex(ValueError,'INTEGRITY_FAILURE'): Memory(self.path,os.urandom(32),self.config)
        head=self.m.current()['checkpoint']['controlDigest']
        obj=self.m.db.execute('SELECT object FROM checkpoints WHERE digest=?',(head,)).fetchone()[0]
        self.m.db.execute('UPDATE objects SET ciphertext=? WHERE id=?',(b'corrupt',obj))
        with self.assertRaisesRegex(ValueError,'INTEGRITY_FAILURE'): self.m.current()
    def test_response_pointer_swapping_cannot_cross_request_boundary(self):
        a=self.wire('context',{});self.m.execute(a)
        b=self.wire('inbox',{});self.m.execute(b)
        target=self.m.db.execute('SELECT result FROM receipts WHERE nonce=?',(b['auth']['nonce'],)).fetchone()[0]
        self.m.db.execute('UPDATE receipts SET result=? WHERE nonce=?',(target,a['auth']['nonce']))
        with self.assertRaisesRegex(ValueError,'INTEGRITY_FAILURE'): self.m.execute(a)
    def test_app_cannot_prepare_or_forge_owner_commit(self):
        with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'): self.m.execute(self.wire('prepare',{'accept':[],'reject':[],'grants':[]}))
        p=self.proposal();self.m.execute(self.wire('proposals',p))
        review=self.m.execute(self.wire('prepare',{'accept':[p['id']],'reject':[],'grants':None},V['testOwnerKey']))
        cp=review['checkpoint'];bad=sign(V['testAppKey'],V['domain'],'Checkpoint',cp)
        with self.assertRaisesRegex(ValueError,'WRONG_SIGNER'): self.m.execute(self.wire('commit',{'checkpoint':cp,'signature':bad},V['testOwnerKey']))
    def test_retraction_removes_current_content_and_history_stays_scoped(self):
        p=self.proposal();self.m.execute(self.wire('proposals',p))
        self.approve({'accept':[p['id']],'reject':[],'grants':None})
        retract=self.proposal();retract['records']=[];retract['sources']=[]
        retract['retractIds']=[p['records'][0]['id']]
        self.m.execute(self.wire('proposals',retract))
        self.approve({'accept':[retract['id']],'reject':[],'grants':None})
        current=self.m.execute(self.wire('context',{}))
        self.assertEqual(current['records'],[])
        payload={'checkpointDigest':current['checkpoint']['controlDigest']}
        with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'):
            self.m.execute(self.wire('history',payload))
        historical=self.m.execute(self.wire('history',payload,V['testOwnerKey']))
        self.assertEqual(historical['records'][0]['content'],p['records'][0]['content'])
        self.assertEqual(historical['snapshot']['records'][0]['disposition'],'retracted')

    def test_expired_request_does_not_touch_database(self):
        wire=self.wire('context',{})
        with self.assertRaisesRegex(ValueError,'EXPIRED_REQUEST'): self.m.execute(wire,now=int(wire['auth']['deadline'])+1)
        self.assertEqual(self.m.db.execute('SELECT count(*) FROM receipts').fetchone()[0],0)

if __name__=='__main__':unittest.main()

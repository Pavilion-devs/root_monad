import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'tests')]
import test_memory
from eth_account import Account
from mcp_bridge import Bridge,create_server

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_memory.MemoryTests();self.fixture.setUp();self.m=self.fixture.m
        self.directory=tempfile.TemporaryDirectory();self.key=test_memory.V['testAppKey']
        self.config={**self.fixture.config,'serviceId':self.m.current()['control']['serviceId']}
        self.profile={'url':'https://memory.example','config':self.config,'application':Account.from_key(self.key).address.lower()}
        self.bridge=Bridge(self.profile,self.key,self.directory.name);self.operations=[]
        def caller(url,config,key,op,payload):
            self.operations.append(op);return self.m.execute(self.fixture.wire(op,payload,key))
        self.caller=caller;self.mock=patch('mcp_bridge.call',caller);self.mock.start()
    def tearDown(self):self.mock.stop();self.directory.cleanup();self.fixture.tearDown()
    def arguments(self):return ('example-1',self.m.current()['checkpoint']['controlDigest'],'A pending observation')
    def test_pending_proposal_does_not_change_current_and_retries_are_deduplicated(self):
        before=self.bridge.read();args=self.arguments();first=self.bridge.propose(*args);second=self.bridge.propose(*args)
        self.assertEqual(first['status'],'pending_owner_review');self.assertEqual(second['proposalId'],first['proposalId'])
        self.assertEqual(self.operations.count('proposals'),1);self.assertEqual(self.bridge.read(),before)
        self.assertNotIn(args[2].encode(),(Path(self.directory.name)/'example-1.enc').read_bytes())
        with self.assertRaisesRegex(ValueError,'REQUEST_ID_CONFLICT'):self.bridge.propose(args[0],args[1],'Different')
    def test_lost_response_reconciles_the_saved_proposal(self):
        def lost(url,config,key,op,payload):
            result=self.caller(url,config,key,op,payload)
            if op=='proposals':raise TimeoutError()
            return result
        args=self.arguments()
        with patch('mcp_bridge.call',lost),self.assertRaises(TimeoutError):self.bridge.propose(*args)
        result=self.bridge.propose(*args)
        self.assertEqual(result['status'],'already_submitted');self.assertEqual(self.operations.count('proposals'),1)
    def test_stale_revision_and_revocation_fail_closed(self):
        args=self.arguments();self.fixture.approve({'accept':[],'reject':[],'grants':self.m.current()['control']['grants']})
        with self.assertRaisesRegex(ValueError,'BASE_CONFLICT'):self.bridge.propose(*args)
        self.fixture.approve({'accept':[],'reject':[],'grants':[]})
        with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'):self.bridge.read()
        with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'):self.bridge.propose(*self.arguments())
    def test_paths_and_owner_identity_cannot_be_supplied(self):
        with self.assertRaisesRegex(ValueError,'INVALID_REQUEST_ID'):self.bridge.propose('../escape','bad','text')
        owner=test_memory.V['testOwnerKey'];profile={**self.profile,'application':Account.from_key(owner).address.lower()}
        with self.assertRaisesRegex(ValueError,'APPLICATION_KEY_REQUIRED'):Bridge(profile,owner,self.directory.name)
    def test_tool_surface_has_no_owner_or_signing_capability(self):
        tools=asyncio.run(create_server(self.bridge).list_tools())
        self.assertEqual({t.name for t in tools},{'memory_current','memory_propose'})
        text=json.dumps([t.model_dump() for t in tools])
        self.assertNotIn(self.key,text);self.assertNotIn('applicationKey',text)
    def test_tampered_context_is_not_returned(self):
        p=self.fixture.proposal();self.m.execute(self.fixture.wire('proposals',p))
        self.fixture.approve({'accept':[p['id']],'reject':[],'grants':None})
        bad=self.m.context(self.m.current(),False);bad['records'][0]['content']='Unverified content'
        with patch('mcp_bridge.call',return_value=bad),self.assertRaisesRegex(ValueError,'CONTENT_MISMATCH'):self.bridge.read()

if __name__=='__main__':unittest.main()

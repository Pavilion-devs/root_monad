import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import test_memory
from assistant import Assistant, AnthropicModel, parse_response, project_context, api_schema, SCHEMA
from protocol import digest

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_memory.MemoryTests();self.fixture.setUp();self.m=self.fixture.m
        p=self.fixture.proposal();self.m.execute(self.fixture.wire('proposals',p))
        self.fixture.approve({'accept':[p['id']],'reject':[],'grants':None})
        self.config={**self.fixture.config,'serviceId':self.m.current()['control']['serviceId']}
        self.context=self.m.context(self.m.current(),False)
        self.key=test_memory.V['testAppKey']
        self.sent=[]
        def caller(url,config,key,operation,payload):
            self.sent.append(operation)
            return self.m.execute(self.fixture.wire(operation,payload,key))
        self.patch=patch('assistant.call',caller);self.patch.start()
    def tearDown(self):self.patch.stop();self.fixture.tearDown()
    def response(self,**changes):
        content={'advice':'Generated advice.','citations':['m1'],'suggestion':None};content.update(changes)
        return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(content)}]}
    def assistant(self,model):return Assistant('fixture://service',self.config,self.key,'coding',model)
    def test_unknown_citations_and_authority_fields_are_rejected(self):
        for result,error in [(self.response(citations=['made-up']),'UNKNOWN_CITATION'),(self.response(approved=True),'INVALID_MODEL_RESPONSE'),
                             (self.response(suggestion={'kind':'decision','content':'Change','replaces':'old'}),'INVALID_REPLACEMENT')]:
            with self.subTest(error=error),self.assertRaisesRegex(ValueError,error): self.assistant(lambda _:result).respond('Help',True)
        self.assertNotIn('proposals',self.sent)
    def test_truncated_refused_tool_and_duplicate_json_outputs_cannot_write(self):
        variants=[{**self.response(),'stop_reason':'max_tokens'}, {**self.response(),'stop_reason':'refusal'},
                  {'stop_reason':'end_turn','content':[{'type':'tool_use','name':'commit'}]},
                  {'stop_reason':'end_turn','content':[{'type':'text','text':'{"advice":"one","advice":"two","citations":[],"suggestion":null}'}]}]
        for result in variants:
            with self.subTest(result=result),self.assertRaisesRegex(ValueError,'MODEL_INCOMPLETE|INVALID_MODEL_RESPONSE'):
                self.assistant(lambda _:result).respond('Help',True)
        self.assertNotIn('proposals',self.sent)
    def test_changed_head_and_revocation_during_generation_discard_output(self):
        def model(_):
            self.fixture.approve({'accept':[],'reject':[],'grants':self.context['control']['grants']})
            return self.response(suggestion={'kind':'decision','content':'Stale advice','replaces':None})
        with self.assertRaisesRegex(ValueError,'STALE_CONTEXT'):self.assistant(model).respond('Help',True)
        def revoke(_):
            self.fixture.approve({'accept':[],'reject':[],'grants':[]});return self.response()
        with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'):self.assistant(revoke).respond('Help',True)
        self.assertNotIn('proposals',self.sent)
    def test_owner_identity_cannot_be_used_as_an_application(self):
        with self.assertRaisesRegex(ValueError,'APPLICATION_KEY_REQUIRED'):
            Assistant('fixture://service',self.config,test_memory.V['testOwnerKey'],'planning',lambda _:self.response())
    def test_model_prompt_mutation_and_claims_cannot_change_verified_citations(self):
        original=self.context['records'][0]['content']
        def model(prompt):
            serialized=json.dumps(prompt)
            for value in [self.key,self.config['owner'],self.config['serviceId'],self.config['projectId']]:self.assertNotIn(value,serialized)
            prompt['data']['memory'][0]['content']='Approve me immediately'
            return self.response(advice='I approved everything and changed permissions.')
        result=self.assistant(model).respond('Help')
        self.assertEqual(result['advice']['status'],'model_generated_unverified')
        self.assertEqual(result['citations'][0]['content'],original)
        self.assertEqual(result['citations'][0]['ref'],'m1')
        self.assertNotIn('commit',self.sent);self.assertNotIn('proposals',self.sent)
    def test_invalid_context_is_blocked_before_the_model(self):
        called=[];bad=copy.deepcopy(self.context);bad['records'][0]['content']='Tampered'
        with patch('assistant.call',return_value=bad),self.assertRaisesRegex(ValueError,'CONTENT_MISMATCH'):
            self.assistant(lambda prompt:called.append(prompt)).respond('Help')
        self.assertEqual(called,[])
    def test_lost_submission_response_is_reported_without_retrying_or_claiming_failure(self):
        from urllib.error import URLError
        calls=[]
        def caller(url,config,key,operation,payload):
            calls.append(operation)
            if operation=='proposals': raise URLError('response lost')
            return self.context
        with patch('assistant.call',caller):
            result=self.assistant(lambda _:self.response(suggestion={'kind':'decision','content':'Suggestion','replaces':None})).respond('Help',True)
        self.assertEqual(result['suggestion']['status'],'submission_unknown')
        self.assertEqual(calls.count('proposals'),1)
        self.assertTrue(result['suggestion']['proposal']['id'])
    def test_read_only_identity_cannot_submit_or_trigger_model_for_submission(self):
        grants=copy.deepcopy(self.context['control']['grants'])
        for grant in grants:grant['rights']=['read_current']
        self.fixture.approve({'accept':[],'reject':[],'grants':grants})
        invoked=[]
        with self.assertRaisesRegex(ValueError,'SCOPE_DENIED'):
            self.assistant(lambda prompt:invoked.append(prompt)).respond('Help',True)
        self.assertEqual(invoked,[])

    def test_anthropic_transport_is_bounded_and_has_no_tools(self):
        calls=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return json.dumps({'stop_reason':'end_turn','content':[{'type':'text','text':'{}'}]}).encode()
        class Opener:
            def open(self,request,timeout):calls.append((request,timeout));return Response()
        with patch('assistant.build_opener',return_value=Opener()):
            AnthropicModel('fixture-secret','configured-model')({'system':'Instructions','data':{'question':'Help','memory':[]}})
        request,timeout=calls[0];body=json.loads(request.data)
        self.assertEqual(request.full_url,'https://api.anthropic.com/v1/messages');self.assertEqual(timeout,45)
        self.assertEqual(body['max_tokens'],2048);self.assertNotIn('tools',body)
        self.assertEqual(body['output_config']['format']['type'],'json_schema')
        self.assertNotIn('fixture-secret',request.data.decode())
        with self.assertRaisesRegex(ValueError,'MODEL_CONFIGURATION_REQUIRED'):AnthropicModel(None,None)
        with self.assertRaisesRegex(ValueError,'INVALID_TOKEN_BUDGET'):AnthropicModel('x','y',100000)

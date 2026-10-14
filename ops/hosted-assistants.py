"""Three live model calls, exact synthetic owner approval, and hosted access revocation."""
import argparse
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from hosted import ROOT, DIRECTORY, ORIGIN, secrets, public_state, save_report
from recovery import seal,unseal,exclusive,sync_directory
from memory import require
from protocol import sign
from client import request
from owner_review import verify_review
from eth_account import Account

OLD='Hosted synthetic project: retain notes for 30 days.'
NEW='Hosted synthetic project: retain notes for 14 days.'
REPORT=ROOT/'results/hosted-assistants.json'
JOURNAL=DIRECTORY/'assistant-journey.enc'
KIND='hosted-assistant-journey/1'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class Journey:
    def __init__(self,env_file):
        self.wallet,self.host=secrets()
        self.key=bytes.fromhex(self.wallet['recoveryKey'])
        self.state=unseal(JOURNAL.read_bytes(),self.key,KIND) if JOURNAL.exists() else {}
        self.config={**self.host['config'],'serviceId':self.host['serviceId'],'registry':{'rpcUrl':'https://testnet-rpc.monad.xyz'}}
        require(self.config['domain']['chainId']==10143,'TESTNET_REQUIRED')
        self.env_file=env_file
        self.live=module('live_journey',ROOT/'scripts/monad-exercise.py')
        self.live.save=lambda:None
        def safe_request(url,body=None):
            require(url.startswith(ORIGIN+'/'),'WRONG_ORIGIN')
            try:return request(url,json.dumps(body).encode() if body is not None else None)
            except HTTPError as error:
                try:code=json.load(error).get('code','HTTP_SERVICE_UNAVAILABLE')
                except Exception:code='HTTP_SERVICE_UNAVAILABLE'
                raise ValueError(code) from None
        self.live.request=safe_request

    def save(self):
        temp=JOURNAL.with_name(JOURNAL.name+'.'+os.urandom(6).hex()+'.tmp')
        exclusive(temp,seal(self.state,self.key,KIND));os.replace(temp,JOURNAL);sync_directory(JOURNAL.parent)
        public={'passed':bool(self.state.get('complete')),'origin':ORIGIN,'projectId':self.config['projectId'],
          'modelMode':'live_anthropic','maxModelCalls':3,'maxOutputTokensPerCall':1536,
          'checks':self.state.get('checks',{}),'calls':self.state.get('calls',[]),'transactions':self.state.get('transactions',[]),
          'steps':[name for name in self.state if not name.startswith('_')],
          'limitations':['Synthetic notes and explicitly authorized automated owner approval; not a user study',
           'Planning/coding are reference adapters sharing one implementation, not third-party app integrations',
           'Three model samples are not a quality benchmark; revoked apps retain previously copied content',
           'Trusted Monad testnet RPC; single reference provider; coding grant is left revoked'],
          'updatedAtUnix':int(time.time())}
        if 'error' in self.state:public['error']=self.state['error']
        REPORT.write_text(json.dumps(public,indent=2)+'\n')

    def stage(self,name,action):
        if name not in self.state:
            self.state[name]=action();self.save()
            print(json.dumps({'completed':name}),flush=True)
        return self.state[name]

    def call(self,role,op,payload):
        return self.live.call(ORIGIN,self.config,self.wallet[role+'Key'],op,payload)

    def read(self,role='planning'):
        bundle=self.call(role,'context',{});self.live.verify_both(self.config,bundle);return bundle

    def model(self,name,role,question):
        # Recover a response saved just before the surrounding stage marker.
        saved=[c for c in self.state.get('calls',[]) if c['step']==name]
        if saved:
            require(len(saved)==1 and saved[0].get('ok'),'SAVED_MODEL_FAILED')
            return saved[0]['result']
        require(name not in self.state.get('_modelAttempts',[]),'MODEL_ATTEMPT_UNCERTAIN')
        require(len(self.state.get('_modelAttempts',[]))<3,'MODEL_BUDGET_EXCEEDED')
        self.state.setdefault('_modelAttempts',[]).append(name);self.save()
        payload={'envFile':self.env_file,'url':ORIGIN,'config':self.config,'applicationKey':self.wallet[role+'Key'],
                 'role':role,'question':question,'submit':False}
        result=subprocess.run([sys.executable,str(ROOT/'scripts/live-assistant.py')],input=json.dumps(payload).encode(),capture_output=True,timeout=180,cwd=ROOT)
        output=json.loads(result.stdout)
        self.state.setdefault('calls',[]).append({'step':name,'question':question,**output});self.save()
        require(result.returncode==0 and output.get('ok'),output.get('code','MODEL_FAILED'))
        return output['result']

    def initial(self):
        bundle=self.read()
        require(len(bundle['records'])==1 and bundle['records'][0]['content']==OLD,'UNEXPECTED_STARTING_MEMORY')
        require(bundle['checkpoint']['controlDigest']==public_state()['acceptedDigest'],'UNEXPECTED_STARTING_HEAD')
        return bundle

    def propose(self,draft):
        p=draft['suggestion']['proposal'];before=self.state['initial']
        require(draft['checkpoint']==before['checkpoint']['controlDigest'],'STALE_CONTEXT')
        require(len(p['records'])==1 and p['records'][0]['kind']=='decision' and p['records'][0]['content']==NEW,'UNEXPECTED_MODEL_PROPOSAL')
        require(p['records'][0]['replaces']==before['records'][0]['id'] and p['retractIds']==[],'UNEXPECTED_MODEL_PROPOSAL')
        require(any(c['recordId']==before['records'][0]['id'] for c in draft['citations']),'MISSING_CURRENT_CITATION')
        inbox=self.call('planning','inbox',{})
        existing=[item for item in inbox['proposals'] if item['proposal']['id']==p['id']]
        if existing:
            require(existing[0]['proposal']==p and existing[0]['status']=='pending','PROPOSAL_STATE_CHANGED')
        else:self.call('planning','proposals',p)
        current=self.read('coding')
        require(current['checkpoint']==before['checkpoint'] and current['records']==before['records'],'PENDING_PROMOTED')
        return p

    def approve(self,name,before,proposal=None,grants=None):
        payload={'accept':[proposal['id']] if proposal else [],'reject':[],'grants':grants}
        review=self.stage('_'+name+'Review',lambda:self.call('owner','prepare',payload))
        verify_review(self.config,before,review,proposal,grants)
        current=self.read()
        if current['checkpoint']['controlDigest']!=review['checkpoint']['controlDigest']:
            require(current['checkpoint']==before['checkpoint'],'UNEXPECTED_CURRENT_HEAD')
            # A persisted expired review is not silently replaced or signed.
            require(int(review['checkpoint']['deadline'])>int(time.time()),'REVIEW_EXPIRED')
            ack=self.live.commit(ORIGIN,self.config,self.wallet['ownerKey'],review)
            self.state.setdefault('transactions',[]).append(ack);self.save()
            current=self.read()
        require(current['checkpoint']['controlDigest']==review['checkpoint']['controlDigest'],'WRONG_ACCEPTED_HEAD')
        require(current['snapshot']==review['snapshot'] and current['control']==review['control'],'UNEXPECTED_ACCEPTED_STATE')
        report=public_state();report.setdefault('originalAcceptedDigest',report['acceptedDigest'])
        report['acceptedDigest']=current['checkpoint']['controlDigest'];report['expectedRecords']=current['records']
        report['latestJourneyReport']=str(REPORT.relative_to(ROOT));save_report(report)
        return current

    def check_coding(self,answer,record,number):
        require(answer['suggestion'] is None,'UNEXPECTED_SUGGESTION')
        require(any(c['recordId']==record['id'] and c['content']==record['content'] for c in answer['citations']),'MISSING_CURRENT_CITATION')
        require(str(number) in answer['advice']['text'],'WRONG_ADVICE')
        return True

    def revoke(self):
        before=self.state['accepted']
        coding=Account.from_key(self.wallet['codingKey']).address.lower()
        grants=[g for g in before['control']['grants'] if g['application']!=coding]
        require(len(grants)==len(before['control']['grants'])-1,'EXPECTED_CODING_GRANT_MISSING')
        return self.approve('revoke',before,grants=grants)

    def denied(self):
        self.live.expect('SCOPE_DENIED',lambda:self.call('coding','context',{}))
        # A new adapter must fail before it can disclose memory to the model.
        from assistant import Assistant
        invoked=[]
        adapter=Assistant(ORIGIN,self.config,self.wallet['codingKey'],'coding',lambda p:invoked.append(p))
        self.live.expect('SCOPE_DENIED',lambda:adapter.respond('What should I implement next?'))
        require(not invoked,'REVOKED_MODEL_CALLED')
        current=self.read();require(current['records']==self.state['accepted']['records'],'REVOCATION_CHANGED_CONTENT')
        return True

    def run(self):
        if self.state.get('complete'):
            self.denied();print(json.dumps({'passed':True,'alreadyComplete':True,'newModelCalls':0}),flush=True);return
        before=self.stage('initial',self.initial)
        draft=self.stage('planning',lambda:self.model('planning','planning',
          'Propose exactly one correction to the current retention decision. The replacement content must be exactly: '+NEW+
          ' Use the current record alias in replaces. Cite the current accepted decision and explain that this suggestion needs owner approval. Keep advice under 100 words.'))
        p=self.stage('pending',lambda:self.propose(draft))
        first=self.stage('codingBeforeApproval',lambda:self.model('codingBeforeApproval','coding',
          'What retention rule should the code implement right now? Cite the accepted memory and give one implementation check. Do not propose changes; use a null suggestion. Keep advice under 100 words.'))
        self.check_coding(first,before['records'][0],30)
        accepted=self.stage('accepted',lambda:self.approve('accept',before,proposal=p))
        require(accepted['records']==p['records'],'WRONG_CORRECTION')
        second=self.stage('codingAfterApproval',lambda:self.model('codingAfterApproval','coding',
          'What retention rule should the code implement right now? Cite the accepted memory and give one implementation check without claiming execution. Do not propose changes; use a null suggestion. Keep advice under 100 words.'))
        self.check_coding(second,p['records'][0],14)
        planning=self.stage('planningSeesCorrection',lambda:self.read('planning'))
        require(planning['records']==p['records'],'PLANNING_MISSED_CORRECTION')
        self.stage('revoked',self.revoke)
        self.stage('revocationChecked',self.denied)
        self.state['checks']={'planningProposedCorrection':True,'pendingNotCurrent':True,'codingUsedThirtyBeforeApproval':True,
          'exactOwnerApprovalVerified':True,'codingUsedFourteenAfterApproval':True,'bothAppsSeeCorrection':True,
          'revokedReadDenied':True,'revokedModelNotInvoked':True,'pythonAndTypescriptVerified':True}
        self.state.pop('error',None);self.state['complete']=True;self.save()
        print(json.dumps({'passed':True,'modelCalls':len(self.state['calls']),'report':str(REPORT)}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--approve-synthetic',action='store_true',required=True,help='Authorize only the exact 30-to-14-day correction and coding grant removal on the existing synthetic test project')
    parser.add_argument('--env-file',required=True)
    args=parser.parse_args()
    os.chdir(ROOT)
    with open(DIRECTORY/'assistant-journey.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        journey=Journey(args.env_file)
        try:journey.run()
        except Exception as error:
            code=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else type(error).__name__
            journey.state['error']=code;journey.save();print(json.dumps({'passed':False,'code':code}),flush=True);return 1
    return 0

if __name__=='__main__':sys.exit(main())

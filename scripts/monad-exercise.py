"""Opt-in live testnet journey using synthetic memory and locally protected identities."""
import copy
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from eth_account import Account
from protocol import digest,sign,project_id
from client import verify
from memory import require,ZERO
from testnet_wallet import STATE,load,exclusive_json
from monad_deploy import adapter
from admin import run as admin
from recovery import exclusive,seal as seal_local,unseal as unseal_local

REPORT=Path('results/monad-live.json')
report={'passed':False,'network':'monad_testnet','chainId':10143,'startedAtUnix':int(time.time()),'checks':{},'transactions':[],'samples':[],
 'limitations':['Synthetic project and automated owner approvals; not a user study','Trusted public RPC; no light-client proof','Two isolated instances of the same reference provider','Memory services run locally; only the registry is on Monad','No model calls in this chain exercise']}

def save():REPORT.write_text(json.dumps(report,indent=2)+'\n')
def progress(step):save();print(json.dumps({'step':step}),flush=True)
def random_id():return '0x'+os.urandom(32).hex()

class Service:
    def __init__(self,startup):
        self.child=subprocess.Popen(['.venv/bin/python','python/server.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.child.stdin.write(json.dumps(startup).encode()+b'\n');self.child.stdin.close()
        ready,_,_=select.select([self.child.stdout],[],[],60)
        if not ready:self.stop();raise ValueError('SERVICE_START_TIMEOUT')
        line=self.child.stdout.readline()
        if not line:self.stop();raise ValueError('SERVICE_START_FAILED')
        self.url=json.loads(line)['url']
    def stop(self):
        if self.child.poll() is None:self.child.terminate();self.child.wait(timeout=10)

def request(url,body=None):
    req=Request(url,json.dumps(body).encode() if body else None,{'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=120) as response:return json.load(response)
    except HTTPError as error:
        code=json.load(error).get('code','REQUEST_FAILED')
        raise ValueError(code) from None

def wire(config,key,base,op,payload):
    body={'formatVersion':'0','projectId':config['projectId'],'method':'POST','path':f"/v0/projects/{config['projectId']}/{op}",'operation':op,'payload':payload}
    auth={'projectId':config['projectId'],'serviceId':config['serviceId'],'checkpointDigest':base,'requestDigest':digest('request',body),'nonce':random_id(),'deadline':str(int(time.time())+240)}
    return {'auth':auth,'body':body,'signature':sign(key,config['domain'],'Request',auth)}

def send(url,value):return request(url+value['body']['path'],value)
def call(url,config,key,op,payload):
    started=time.monotonic();base=request(url+'/head')['checkpointDigest']
    result=send(url,wire(config,key,base,op,payload))
    report['samples'].append({'operation':op,'elapsedSeconds':round(time.monotonic()-started,3)})
    return result

def expect(code,action):
    try:action()
    except ValueError as error:require(str(error)==code,'UNEXPECTED_REJECTION');return
    raise ValueError('EXPECTED_REJECTION_MISSING')

def proposal(config,key,base,text,replaces=None):
    sid=random_id()
    return {'formatVersion':'0','projectId':config['projectId'],'id':random_id(),'author':Account.from_key(key).address.lower(),'baseCheckpoint':base,
      'records':[{'formatVersion':'0','projectId':config['projectId'],'id':random_id(),'kind':'decision','content':text,'author':Account.from_key(key).address.lower(),'sourceIds':[sid],'replaces':replaces}],
      'sources':[{'formatVersion':'0','projectId':config['projectId'],'id':sid,'kind':'application_observation','speaker':'Synthetic test client','excerpt':text,'locator':None,'occurredAt':None}],'retractIds':[]}

def commit(url,config,key,review):
    require(digest('control',review['control'])==review['checkpoint']['controlDigest'],'CONTENT_MISMATCH')
    require(digest('snapshot',review['snapshot'])==review['control']['snapshotDigest'],'CONTENT_MISMATCH')
    payload={'checkpoint':review['checkpoint'],'signature':sign(key,config['domain'],'Checkpoint',review['checkpoint'])}
    value=wire(config,key,review['checkpoint']['previousDigest'],'commit',payload)
    started=time.monotonic()
    while True:
        try:result=send(url,value);break
        except ValueError as error:
            if str(error)!='COMMIT_PENDING' or time.monotonic()-started>90:raise
            time.sleep(1)
    report['samples'].append({'operation':'commit_to_verified_ack','elapsedSeconds':round(time.monotonic()-started,3)})
    report['transactions'].append(result);save();return result

def verify_both(config,bundle):
    verify(config,bundle)
    result=subprocess.run(['node_modules/.bin/tsx','scripts/verify-monad-context.ts'],input=json.dumps({'config':config,'bundle':bundle}).encode(),capture_output=True,timeout=90)
    require(result.returncode==0 and json.loads(result.stdout)['verified'],'INDEPENDENT_VERIFICATION_FAILED')

def migrate(wallet,directory,config,client,source,genesis,records=None):
    rpc=source['registry'];domain=config['domain'];registry=adapter(domain['verifyingContract'])
    project=config['projectId'];owner=config['owner'];cp=genesis['checkpoint']
    phase_path=directory/'migration-state.enc'
    if phase_path.exists():phase=unseal_local(phase_path.read_bytes(),bytes.fromhex(wallet['recoveryKey']),'live-migration-state/1')
    else:
        if records is None:
            from memory import Memory
            memory=Memory(source['db'],bytes.fromhex(source['key']),config,registry=registry)
            try:records=memory.context(memory.current(),False)['records']
            finally:memory.close()
        phase={'records':records,'binding':{'serviceId':random_id(),'storage':{'providerId':random_id(),'locator':'local://monad-live/provider-b'}}}
        exclusive(phase_path,seal_local(phase,bytes.fromhex(wallet['recoveryKey']),'live-migration-state/1'))
    b=None
    try:
        archive=directory/'recovery.enc';recovery_file=directory/'recovery.key'
        if not archive.exists():
            admin({**source,'operation':'export','archive':str(archive),'recoveryKeyFile':str(recovery_file)})
        progress('encrypted_export_ready')
        recovery_key=recovery_file.read_text().strip()
        binding=phase['binding']
        target_dir=directory/'provider-b'
        if not target_dir.exists():
            admin({'operation':'restore','config':config,'registry':rpc,'archive':str(archive),'recoveryKey':recovery_key,'binding':binding,'directory':str(target_dir)})
        progress('encrypted_restore_ready')
        target={'db':str(target_dir/'memory.sqlite'),'keyEnvelope':str(target_dir/'project-key.enc'),'recoveryKey':recovery_key,'config':config,'registry':rpc,'relayerKey':wallet['relayerKey']}
        review_path=directory/'migration-review.enc'
        if review_path.exists(): review=unseal_local(review_path.read_bytes(),bytes.fromhex(wallet['recoveryKey']),'live-migration-review/1')
        else:
            review=admin({**target,'operation':'prepare-migration'})
            exclusive(review_path,seal_local(review,bytes.fromhex(wallet['recoveryKey']),'live-migration-review/1'))
        payload={'checkpoint':review['checkpoint'],'signature':sign(wallet['ownerKey'],domain,'Checkpoint',review['checkpoint'])}
        began=time.monotonic()
        while True:
            try:ack=admin({**target,'operation':'commit-migration','payload':payload});break
            except ValueError as error:
                if str(error)!='COMMIT_PENDING' or time.monotonic()-began>90:raise
                time.sleep(1)
        if not any(t['transactionHash']==ack['transactionHash'] for t in report['transactions']):report['transactions'].append(ack)
        b=Service(target);fresh={**client,'serviceId':binding['serviceId']}
        expect('WRONG_AUDIENCE',lambda:call(b.url,client,wallet['planningKey'],'context',{}))
        migrated=call(b.url,fresh,wallet['planningKey'],'context',{});verify_both(fresh,migrated)
        require(migrated['records']==phase['records'],'MIGRATION_CONTENT_CHANGED')
        expect('SCOPE_DENIED',lambda:call(b.url,fresh,wallet['codingKey'],'context',{}))
        follow=proposal(fresh,wallet['planningKey'],migrated['checkpoint']['controlDigest'],'A new proposal works after migration.')
        call(b.url,fresh,wallet['planningKey'],'proposals',follow)
        report['checks'].update(sourceServiceStopped=True,encryptedMigration=True,oldAudienceRejected=True,continuedReadAndProposalAfterMigration=True,revocationPreservedAcrossMigration=True)
        progress('migration_passed')
        # Capture genesis plus all accepted updates directly from finalized registry evidence.
        history=call(b.url,fresh,wallet['planningKey'],'history',{'checkpointDigest':cp['controlDigest']})
        verify(fresh,history,cp['controlDigest']);report['checks']['historicalReadAfterMigration']=True
        view=registry.view(project);genesis_event=registry.accepted(cp,owner,view)
        hashes=[genesis_event['transactionHash']]+[t['transactionHash'] for t in report['transactions']]
        receipts=[]
        for transaction_hash in hashes:
            receipt=registry.receipt({'transactionHash':transaction_hash});require(receipt and receipt['status']=='0x1','FINAL_RECEIPT_MISSING')
            receipts.append({'transactionHash':transaction_hash,'blockNumber':receipt['blockNumber'],'gasUsed':str(int(receipt['gasUsed'],16)),
              'feeWei':str(int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16))})
        report['receipts']=receipts;report['transactionFeesWei']=str(sum(int(r['feeWei']) for r in receipts))
        report['finalSequence']=view['sequence'];report['passed']=True;report['finishedAtUnix']=int(time.time())
        progress('live_exercise_passed')
    finally:
        if b:b.stop()
        registry.close()

def resume_migration():
    global report
    report=json.loads(REPORT.read_text())
    require(report['checks'].get('revocationBlocksFreshAndCachedRead') and not report['passed'],'NO_MIGRATION_TO_RESUME')
    if 'error' in report:report.setdefault('interruptions',[]).append({'code':report.pop('error'),'resumedAtUnix':int(time.time())})
    wallet=load();directory=Path(report['stateDirectory'])
    require(directory.parent==STATE,'WRONG_STATE_DIRECTORY')
    stored=json.loads((directory/'project.json').read_text());config=stored['config'];client=stored['client']
    require(config['owner']==Account.from_key(wallet['ownerKey']).address.lower(),'WRONG_SIGNER')
    source={'db':str(directory/'memory.sqlite'),'key':wallet['storageKey'],'config':config,'registry':client['registry'],'relayerKey':wallet['relayerKey']}
    progress('resuming_saved_migration')
    migrate(wallet,directory,config,client,source,stored['genesis'])

def main():
    wallet=load();deployment=json.loads(Path('results/monad-deployment.json').read_text())
    domain={'name':'PortableMemory','version':'0','chainId':10143,'verifyingContract':deployment['contractAddress']}
    registry=adapter(deployment['contractAddress']);block=registry.block()
    require('0x'+__import__('eth_utils').keccak(bytes.fromhex(registry.rpc('eth_getCode',[deployment['contractAddress'],block['number']])[2:])).hex()==deployment['runtimeCodeHash'],'REGISTRY_CODE_CHANGED')
    nonce=random_id();owner=Account.from_key(wallet['ownerKey']).address.lower();project=project_id(owner,nonce)
    directory=STATE/('exercise-'+str(int(time.time())));directory.mkdir(mode=0o700)
    config={'projectId':project,'owner':owner,'domain':domain};service_id=random_id()
    rpc={'rpcUrl':registry.url,'maxTransactionFeeWei':'100000000000000000'}
    client={**config,'serviceId':service_id,'registry':rpc}
    snap={'formatVersion':'0','projectId':project,'previousDigest':ZERO,'records':[],'sources':[],'currentIds':[],'resolutions':[]}
    control={'formatVersion':'0','projectId':project,'sequence':'0','previousDigest':ZERO,'creationNonce':nonce,'snapshotDigest':digest('snapshot',snap),'serviceId':service_id,
      'grants':sorted([{'application':Account.from_key(wallet[role+'Key']).address.lower(),'serviceId':service_id,'rights':['propose','read_current','read_history'],'expiresAt':str(int(time.time())+86400)} for role in ('planning','coding')],key=lambda g:g['application']),
      'storage':{'providerId':random_id(),'locator':'local://monad-live/provider-a'},'salt':random_id()}
    cp={'projectId':project,'sequence':'0','previousDigest':ZERO,'controlDigest':digest('control',control),'deadline':str(int(time.time())+300)}
    genesis={'checkpoint':cp,'control':control,'snapshot':snap,'signature':sign(wallet['ownerKey'],domain,'Checkpoint',cp)}
    startup={'db':str(directory/'memory.sqlite'),'key':wallet['storageKey'],'config':config,'genesis':genesis,'registry':rpc,'relayerKey':wallet['relayerKey']}
    exclusive_json(directory/'project.json',{'config':config,'client':client,'genesis':genesis})
    report.update(projectId=project,contractAddress=deployment['contractAddress'],stateDirectory=str(directory));progress('starting_live_genesis')
    a=b=None
    try:
        a=Service(startup);initial=call(a.url,client,wallet['planningKey'],'context',{});verify_both(client,initial)
        report['checks']['liveGenesisAndIndependentClients']=True;progress('genesis_finalized')
        seed=proposal(client,wallet['planningKey'],cp['controlDigest'],'Retain synthetic project notes for 30 days.')
        call(a.url,client,wallet['planningKey'],'proposals',seed)
        review=call(a.url,client,wallet['ownerKey'],'prepare',{'accept':[seed['id']],'reject':[],'grants':None})
        commit(a.url,client,wallet['ownerKey'],review)
        first=call(a.url,client,wallet['codingKey'],'context',{});verify_both(client,first)
        require(first['records'][0]['content']==seed['records'][0]['content'],'WRONG_CURRENT_MEMORY')
        report['checks']['crossApplicationAcceptedMemory']=True;progress('cross_app_read_passed')
        change=proposal(client,wallet['planningKey'],first['checkpoint']['controlDigest'],'Retain synthetic project notes for 14 days.',seed['records'][0]['id'])
        call(a.url,client,wallet['planningKey'],'proposals',change)
        still=call(a.url,client,wallet['codingKey'],'context',{})
        require(still['checkpoint']==first['checkpoint'],'UNAPPROVED_PROMOTION')
        left=call(a.url,client,wallet['ownerKey'],'prepare',{'accept':[change['id']],'reject':[],'grants':None})
        right=call(a.url,client,wallet['ownerKey'],'prepare',{'accept':[change['id']],'reject':[],'grants':None})
        commit(a.url,client,wallet['ownerKey'],left)
        expect('BASE_CONFLICT',lambda:commit(a.url,client,wallet['ownerKey'],right))
        corrected=call(a.url,client,wallet['codingKey'],'context',{});verify_both(client,corrected)
        require(corrected['records'][0]['content']==change['records'][0]['content'],'WRONG_CORRECTION')
        report['checks'].update(pendingNotCurrent=True,competingOwnerApprovalRejected=True,correctionShared=True)
        progress('correction_and_conflict_passed')
        cached=wire(client,wallet['codingKey'],corrected['checkpoint']['controlDigest'],'context',{});send(a.url,cached)
        grants=[g for g in corrected['control']['grants'] if g['application']!=Account.from_key(wallet['codingKey']).address.lower()]
        revoke=call(a.url,client,wallet['ownerKey'],'prepare',{'accept':[],'reject':[],'grants':grants})
        commit(a.url,client,wallet['ownerKey'],revoke)
        expect('SCOPE_DENIED',lambda:send(a.url,cached))
        expect('SCOPE_DENIED',lambda:call(a.url,client,wallet['codingKey'],'context',{}))
        report['checks']['revocationBlocksFreshAndCachedRead']=True;progress('revocation_passed')
        source={k:v for k,v in startup.items() if k!='genesis'}
        a.stop();a=None
        migrate(wallet,directory,config,client,source,genesis,corrected['records'])
    finally:
        if a:a.stop()
        if b:b.stop()
        registry.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--resume-migration',action='store_true')
    parser.add_argument('--output',type=Path,default=REPORT)
    args=parser.parse_args();REPORT=args.output
    if REPORT.exists() and not args.resume_migration:
        parser.error('Report already exists; choose a new --output path to preserve evidence.')
    try:
        if args.resume_migration:resume_migration()
        else:main()
    except Exception as error:
        report['error']=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else type(error).__name__
        save();print(json.dumps({'passed':False,'code':report['error']}),flush=True);sys.exit(1)

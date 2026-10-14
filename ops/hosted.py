"""Bounded Tierhive test deployment. Owner/client keys stay in the local Keychain vault."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from eth_account import Account
from eth_utils import keccak
from memory import Memory,require,ZERO
from protocol import digest,sign,project_id
from recovery import exclusive,seal,unseal
from testnet_wallet import STATE,load,exclusive_json
from monad_deploy import adapter

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=STATE/'hosted-memory'
REPORT=ROOT/'results/hosted-memory.json'
ORIGIN='https://memory.useroot.xyz'
SSH=['ssh','-p','3155','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@57.129.106.133']
KIND='portable-memory-hosted/1'

def remote(command,data=None):
    result=subprocess.run(SSH+[command],input=data,capture_output=True,timeout=180)
    if result.returncode:raise ValueError('REMOTE_OPERATION_FAILED')
    return result.stdout

def save_report(value):
    REPORT.write_text(json.dumps(value,indent=2)+'\n')

def public_state():
    return json.loads(REPORT.read_text()) if REPORT.exists() else {'network':'monad_testnet','origin':ORIGIN,'checks':{}}

def secrets():
    w=load();return w,unseal((DIRECTORY/'state.enc').read_bytes(),bytes.fromhex(w['recoveryKey']),KIND)

def baseline():
    value=public_state();raw=remote('docker ps -q | xargs -r docker inspect --format "{{.Name}} {{.Id}} {{.State.StartedAt}} {{.State.Status}}"').decode().strip().splitlines()
    if 'existingServices' not in value:value['existingServices']=raw;save_report(value)
    else:
        require(all(row in raw for row in value['existingServices']),'EXISTING_SERVICE_CHANGED')
    print(json.dumps({'existingServicesPreserved':True,'count':len(value['existingServices'])}),flush=True)

def prepare():
    DIRECTORY.mkdir(mode=0o700,parents=True,exist_ok=True)
    w=load();wrapping=bytes.fromhex(w['recoveryKey'])
    deployment=json.loads((ROOT/'results/monad-deployment.json').read_text())
    if not (DIRECTORY/'state.enc').exists():
        nonce='0x'+os.urandom(32).hex();owner=Account.from_key(w['ownerKey']).address.lower()
        state={'relayerKey':'0x'+Account.create().key.hex(),'storageKey':os.urandom(32).hex(),'creationNonce':nonce,
         'config':{'owner':owner,'projectId':project_id(owner,nonce),'domain':{'name':'PortableMemory','version':'0','chainId':10143,'verifyingContract':deployment['contractAddress']}},
         'serviceId':'0x'+os.urandom(32).hex(),'providerId':'0x'+os.urandom(32).hex()}
        exclusive(DIRECTORY/'state.enc',seal(state,wrapping,KIND))
    w,s=secrets();r=adapter(deployment['contractAddress']);account=Account.from_key(w['relayerKey']);target=Account.from_key(s['relayerKey']).address
    try:
        block=r.block()
        code=r.rpc('eth_getCode',[deployment['contractAddress'],block['number']])
        require('0x'+keccak(bytes.fromhex(code[2:])).hex()==deployment['runtimeCodeHash'],'REGISTRY_CODE_CHANGED')
        path=DIRECTORY/'funding.enc'
        if not path.exists():
            amount=500_000_000_000_000_000
            gasprice=int(r.rpc('eth_gasPrice',[]),16)
            gas=int(r.rpc('eth_estimateGas',[{'from':account.address,'to':target,'value':hex(amount)}]),16)
            require(gas*gasprice<=10_000_000_000_000_000,'FEE_LIMIT_EXCEEDED')
            require(int(r.rpc('eth_getBalance',[account.address,'latest']),16)>=amount+gas*gasprice,'TESTNET_FUNDS_REQUIRED')
            tx={'chainId':10143,'nonce':int(r.rpc('eth_getTransactionCount',[account.address,'pending']),16),'to':target,'value':amount,'gas':gas,'gasPrice':gasprice}
            signed=account.sign_transaction(tx)
            intent={'rawTransaction':'0x'+signed.raw_transaction.hex(),'transactionHash':'0x'+signed.hash.hex(),'recipient':target,'amountWei':str(amount)}
            exclusive(path,seal(intent,wrapping,'hosted-funding/1'))
        intent=unseal(path.read_bytes(),wrapping,'hosted-funding/1');require(intent['recipient']==target,'WRONG_SIGNER')
        receipt=r.receipt(intent)
        if receipt is None:
            r.broadcast(intent);deadline=time.monotonic()+60
            while receipt is None and time.monotonic()<deadline:
                receipt=r.receipt(intent)
                if receipt is None:time.sleep(1)
        require(receipt and receipt['status']=='0x1','FUNDING_PENDING')
        result=public_state();result.update(projectId=s['config']['projectId'],relayer=target,fundingTransaction=intent['transactionHash'],fundedTestMon='0.5',stateDirectory=str(DIRECTORY))
        save_report(result)
    finally:r.close()
    registry=adapter(deployment['contractAddress'],s['relayerKey'])
    genesispath=DIRECTORY/'genesis.json'
    if genesispath.exists():genesis=json.loads(genesispath.read_text())
    else:
        config=s['config'];project=config['projectId']
        snapshot={'formatVersion':'0','projectId':project,'previousDigest':ZERO,'records':[],'sources':[],'currentIds':[],'resolutions':[]}
        control={'formatVersion':'0','projectId':project,'sequence':'0','previousDigest':ZERO,'creationNonce':s['creationNonce'],'snapshotDigest':digest('snapshot',snapshot),'serviceId':s['serviceId'],
         'grants':sorted([{'application':Account.from_key(w[role+'Key']).address.lower(),'serviceId':s['serviceId'],'rights':['propose','read_current','read_history'],'expiresAt':str(int(time.time())+7*86400)} for role in ('planning','coding')],key=lambda g:g['application']),
         'storage':{'providerId':s['providerId'],'locator':ORIGIN},'salt':'0x'+os.urandom(32).hex()}
        cp={'projectId':project,'sequence':'0','previousDigest':ZERO,'controlDigest':digest('control',control),'deadline':str(int(time.time())+600)}
        genesis={'checkpoint':cp,'control':control,'snapshot':snapshot,'signature':sign(w['ownerKey'],config['domain'],'Checkpoint',cp)}
        exclusive_json(genesispath,genesis)
    deadline=time.monotonic()+60
    try:
        while True:
            try:
                memory=Memory(DIRECTORY/'memory.sqlite',bytes.fromhex(s['storageKey']),s['config'],genesis,registry)
                memory.close();break
            except ValueError as error:
                if str(error)!='COMMIT_PENDING' or time.monotonic()>deadline:raise
                time.sleep(1)
        value=public_state();value['checks']['dedicatedRelayerAndGenesisFinalized']=True;save_report(value)
        print(json.dumps({'prepared':True,'projectId':s['config']['projectId'],'relayer':target}),flush=True)
    finally:registry.close()

def provision():
    baseline();w,s=secrets()
    startup={'db':'/data/memory.sqlite','key':s['storageKey'],'config':s['config'],'registry':{'rpcUrl':'https://testnet-rpc.monad.xyz','maxTransactionFeeWei':'100000000000000000'},
      'relayerKey':s['relayerKey'],'port':8080,'bindHost':'0.0.0.0','publicOrigin':ORIGIN}
    # A first provisioning must never replace an existing deployment or state.
    remote('test ! -e /srv/portable-memory && install -d -m 700 /srv/portable-memory && install -d -m 700 -o 10002 -g 10002 /srv/portable-memory/data /srv/portable-memory/secrets && install -d -m 700 /srv/portable-memory/backups')
    remote('umask 077; cat > /srv/portable-memory/secrets/startup.json; chown 10002:10002 /srv/portable-memory/secrets/startup.json',json.dumps(startup).encode())
    remote('umask 077; cat > /srv/portable-memory/data/memory.sqlite; chown 10002:10002 /srv/portable-memory/data/memory.sqlite',(DIRECTORY/'memory.sqlite').read_bytes())
    remote('umask 077; cat > /srv/portable-memory/nginx.conf',(ROOT/'ops/nginx.conf').read_bytes())
    print(json.dumps({'provisioned':True,'ownerKeyTransferred':False,'clientKeysTransferred':False}),flush=True)

def exercise(mode,url):
    w,s=secrets();value=public_state()
    spec=importlib.util.spec_from_file_location('live',ROOT/'scripts/monad-exercise.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.save=lambda:None
    def request(address,body=None):
        from urllib.error import HTTPError
        headers={'Content-Type':'application/json','Host':'memory.useroot.xyz'}
        try:
            with urlopen(Request(address,json.dumps(body).encode() if body else None,headers),timeout=120) as response:return json.load(response)
        except HTTPError as error:
            try:code=json.load(error).get('code','REQUEST_FAILED')
            except (ValueError,AttributeError):code='HTTP_SERVICE_UNAVAILABLE'
            raise ValueError(code) from None
    m.request=request
    deadline=time.monotonic()+90
    while True:
        try:
            require(request(url+'/healthz')=={'status':'alive'},'SERVICE_NOT_READY');break
        except Exception:
            if time.monotonic()>=deadline:raise
            time.sleep(1)
    client={**s['config'],'serviceId':s['serviceId'],'registry':{'rpcUrl':'https://testnet-rpc.monad.xyz'}}
    bundle=m.call(url,client,w['planningKey'],'context',{});m.verify_both(client,bundle)
    if mode=='write':
        require(bundle['checkpoint']['sequence']=='0','ALREADY_EXERCISED')
        seed=m.proposal(client,w['planningKey'],bundle['checkpoint']['controlDigest'],'Hosted synthetic project: retain notes for 30 days.')
        m.call(url,client,w['planningKey'],'proposals',seed)
        review=m.call(url,client,w['ownerKey'],'prepare',{'accept':[seed['id']],'reject':[],'grants':None})
        ack=m.commit(url,client,w['ownerKey'],review)
        coding=m.call(url,client,w['codingKey'],'context',{});m.verify_both(client,coding)
        require(coding['records'][0]['content']==seed['records'][0]['content'],'WRONG_CONTENT')
        value['acceptedDigest']=coding['checkpoint']['controlDigest'];value['commitTransaction']=ack['transactionHash']
        value['checks']['hostedCrossApplicationApproval']=True
    else:
        require(bundle['checkpoint']['controlDigest']==value['acceptedDigest'],'RESTORE_HEAD_MISMATCH')
        if 'expectedRecords' in value:
            require(bundle['records']==value['expectedRecords'],'WRONG_CONTENT')
        else:
            require(bundle['records'][0]['content']=='Hosted synthetic project: retain notes for 30 days.','WRONG_CONTENT')
        value['checks'][mode]=True
    value.setdefault('samples',[]).extend(m.report['samples']);save_report(value)
    print(json.dumps({'verified':True,'mode':mode,'checkpoint':value.get('acceptedDigest',bundle['checkpoint']['controlDigest'])}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['baseline','prepare','provision','write','restartVerified','backupRestoreVerified','publicHttpsVerified'])
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--url',default='http://127.0.0.1:13014')
    args=parser.parse_args()
    try:
        if args.operation in ('baseline','prepare','provision'):globals()[args.operation]()
        else:exercise(args.operation,args.url)
    except Exception as error:
        print(json.dumps({'failed':True,'code':str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else type(error).__name__}),flush=True)
        sys.exit(1)

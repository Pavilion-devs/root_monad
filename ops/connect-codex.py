"""Grant a separate Codex MCP identity; keep signing authority in the owner process."""
import argparse
import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
from hosted import ROOT,DIRECTORY,ORIGIN,secrets,public_state,save_report
sys.path.insert(0,str(ROOT/'python'))
from eth_account import Account
from client import verify
from memory import require
from owner_review import verify_review
from protocol import sign
from recovery import exclusive,seal,unseal,sync_directory
from mcp_bridge import keychain_key

APPDIR=DIRECTORY/'codex'
PROFILE=APPDIR/'profile.json'
SERVICE='portable-memory.mcp.codex.v1'
ACCOUNT='application'
KIND='portable-memory-codex-grant/1'
JOURNAL=APPDIR/'owner-grant.enc'


def atomic_save(state,wrapping):
    temp=APPDIR/('grant-'+os.urandom(8).hex()+'.tmp')
    exclusive(temp,seal(state,wrapping,KIND));os.replace(temp,JOURNAL);sync_directory(APPDIR)


def provision():
    spec=importlib.util.spec_from_file_location('claude_connection',ROOT/'ops/connect-claude.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    live=helper.live_module()
    wallet,host=secrets();wrapping=bytes.fromhex(wallet['recoveryKey'])
    config={**host['config'],'serviceId':host['serviceId'],'registry':{'rpcUrl':'https://testnet-rpc.monad.xyz'}}
    require(config['domain']['chainId']==10143,'TESTNET_REQUIRED')
    if not PROFILE.exists():
        found=subprocess.run(['/usr/bin/security','find-generic-password','-s',SERVICE,'-a',ACCOUNT,'-w'],capture_output=True)
        if found.returncode==44:
            key='0x'+Account.create().key.hex()
            subprocess.run(['/usr/bin/security','-i'],input=f'add-generic-password -s {SERVICE} -a {ACCOUNT} -w {key}\n'.encode(),capture_output=True,check=True)
        else:require(found.returncode==0,'KEYCHAIN_UNAVAILABLE')
        key=keychain_key(SERVICE,ACCOUNT)
        profile={'url':ORIGIN,'config':config,'application':Account.from_key(key).address.lower(),'keychainService':SERVICE,'keychainAccount':ACCOUNT}
        exclusive(PROFILE,json.dumps(profile,indent=2).encode())
    profile=json.loads(PROFILE.read_text());key=keychain_key(SERVICE,ACCOUNT)
    require(profile['config']==config and profile['application']==Account.from_key(key).address.lower(),'APPLICATION_IDENTITY_MISMATCH')
    claude=json.loads((DIRECTORY/'claude-code/profile.json').read_text())
    require(profile['application'] not in (claude['application'],config['owner']),'DISTINCT_APPLICATION_REQUIRED')
    before=live.call(ORIGIN,config,wallet['ownerKey'],'context',{});live.verify_both(config,before)
    if JOURNAL.exists():state=unseal(JOURNAL.read_bytes(),wrapping,KIND)
    else:
        require(not any(g['application']==profile['application'] for g in before['control']['grants']),'UNEXPECTED_EXISTING_GRANT')
        grant={'application':profile['application'],'serviceId':config['serviceId'],'rights':['propose','read_current'],'expiresAt':str(int(time.time())+7*86400)}
        grants=sorted(before['control']['grants']+[grant],key=lambda g:g['application'])
        review=live.call(ORIGIN,config,wallet['ownerKey'],'prepare',{'accept':[],'reject':[],'grants':grants})
        verify_review(config,before,review,grants=grants)
        state={'before':before,'grants':grants,'review':review};atomic_save(state,wrapping)
    require(state['before']['control']['projectId']==config['projectId'],'WRONG_PROJECT')
    verify_review(config,state['before'],state['review'],grants=state['grants'])
    cp=state['review']['checkpoint']
    if int(before['control']['sequence'])>=int(cp['sequence']):
        accepted=before if before['checkpoint']['controlDigest']==cp['controlDigest'] else live.call(ORIGIN,config,wallet['ownerKey'],'history',{'checkpointDigest':cp['controlDigest']})
        verify(config,accepted,None if accepted is before else cp['controlDigest'])
        require(accepted['control']==state['review']['control'],'UNEXPECTED_GRANT_CHANGE')
    else:
        require(before['checkpoint']==state['before']['checkpoint'],'BASE_CONFLICT')
        require(int(cp['deadline'])>int(time.time()),'REVIEW_EXPIRED')
        if 'wire' not in state:
            payload={'checkpoint':cp,'signature':sign(wallet['ownerKey'],config['domain'],'Checkpoint',cp)}
            state['wire']=live.wire(config,wallet['ownerKey'],cp['previousDigest'],'commit',payload)
            atomic_save(state,wrapping)
        deadline=time.monotonic()+90
        while True:
            try:
                state['ack']=live.send(ORIGIN,state['wire']);atomic_save(state,wrapping);break
            except ValueError as error:
                if str(error)!='COMMIT_PENDING' or time.monotonic()>deadline:raise
                time.sleep(1)
    after=live.call(ORIGIN,config,key,'context',{});live.verify_both(config,after)
    expected=next(g for g in state['grants'] if g['application']==profile['application'])
    require(expected in after['control']['grants'] and int(expected['expiresAt'])>int(time.time()),'GRANT_NO_LONGER_ACTIVE')
    if after['checkpoint']['controlDigest']==cp['controlDigest']:
        require(after['records']==state['before']['records'],'UNEXPECTED_MEMORY_CHANGE')
    report={'passed':True,'application':profile['application'],'profile':str(PROFILE),'rights':expected['rights'],'grantCheckpoint':cp['controlDigest'],'sequence':cp['sequence'],'currentSequence':after['control']['sequence'],'checks':{'distinctIdentity':True,'exactGrantVerified':True,'pythonAndTypescriptVerified':True},'transaction':state.get('ack')}
    (ROOT/'results/codex-identity.json').write_text(json.dumps(report,indent=2)+'\n')
    hosted=public_state();hosted.update(acceptedDigest=after['checkpoint']['controlDigest'],expectedRecords=after['records']);save_report(hosted)
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true',required=True);parser.parse_args()
    APPDIR.mkdir(mode=0o700,parents=True,exist_ok=True)
    try:
        with open(APPDIR/'operator.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);provision()
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else type(error).__name__
        print(json.dumps({'passed':False,'code':code}),flush=True);sys.exit(1)

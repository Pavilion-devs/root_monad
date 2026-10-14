"""Read-only live profile of the existing migrated project; never sends a transaction."""
import copy,json,sys,time,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from memory import Memory,require
from registry import registry_for
from recovery import load_key,unseal
from testnet_wallet import STATE,load
from protocol import digest,sign

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live',action='store_true',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():parser.error('Output already exists; choose a new path.')
label='after'
report=json.loads(Path('results/monad-live.json').read_text());root=Path(report['stateDirectory']);require(root.parent==STATE,'WRONG_STATE_DIRECTORY')
w=load();stored=json.loads((root/'project.json').read_text());config=stored['config']
phase=unseal((root/'migration-state.enc').read_bytes(),bytes.fromhex(w['recoveryKey']),'live-migration-state/1')
key=load_key(root/'provider-b'/'project-key.enc',bytes.fromhex((root/'recovery.key').read_text().strip()),config)
r=registry_for(config['domain'],stored['client']['registry'])
profile={'label':label,'readOnly':True,'startedAtUnix':int(time.time()),'samples':[],'errors':[]}
method_counts={};elapsed_rpc=0;calls=0
original=r.rpc
def counted(method,params):
 global calls,elapsed_rpc
 began=time.perf_counter();calls+=1;method_counts[method]=method_counts.get(method,0)+1
 try:return original(method,params)
 finally:elapsed_rpc+=time.perf_counter()-began
r.rpc=counted
original_many=r.rpc_many
def counted_many(items):
 global calls,elapsed_rpc
 began=time.perf_counter();calls+=len(items)
 for method,_ in items:method_counts[method]=method_counts.get(method,0)+1
 try:return original_many(items)
 finally:elapsed_rpc+=time.perf_counter()-began
if label=='after':r.rpc_many=counted_many
m=Memory(root/'provider-b'/'memory.sqlite',key,config,registry=r)
try:
 for i in range(3):
  before_calls=calls;before_time=elapsed_rpc;before_methods=copy.copy(method_counts)
  before_transport=copy.deepcopy(r._transport.metrics) if getattr(r,'_transport',None) else None
  begin=time.perf_counter()
  try:
   m.recover_intents();base=m.current()['checkpoint']['controlDigest']
   body={'formatVersion':'0','projectId':config['projectId'],'method':'POST','path':f"/v0/projects/{config['projectId']}/context",'operation':'context','payload':{}}
   auth={'projectId':config['projectId'],'serviceId':phase['binding']['serviceId'],'checkpointDigest':base,'requestDigest':digest('request',body),'nonce':'0x'+__import__('os').urandom(32).hex(),'deadline':str(int(time.time())+240)}
   bundle=m.execute({'body':body,'auth':auth,'signature':sign(w['planningKey'],config['domain'],'Request',auth)})
   result={'elapsedSeconds':round(time.perf_counter()-begin,3),'rpcSeconds':round(elapsed_rpc-before_time,3),'rpcCalls':calls-before_calls,
    'methods':{name:count-before_methods.get(name,0) for name,count in method_counts.items()},'checkpoint':bundle['checkpoint']['controlDigest']}
   if before_transport is not None:result['transport']={name:r._transport.metrics[name]-value for name,value in before_transport.items() if isinstance(value,(float,int))}
   profile['samples'].append(result);print(json.dumps(result),flush=True)
  except Exception as error:
   profile['errors'].append({'sample':i,'type':type(error).__name__});raise
finally:
 m.close()
 if hasattr(r,'close'):r.close()
 args.output.write_text(json.dumps(profile,indent=2)+'\n')

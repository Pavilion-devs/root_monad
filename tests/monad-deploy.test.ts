import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Contract,Wallet,keccak256} from 'ethers';
import {localChain,compile} from '../src/chain.js';

test('deployment intent resumes after pre-broadcast interruption on a real local EVM',async()=>{
 const chain=await localChain(10143);const directory=mkdtempSync(join(tmpdir(),'memory-deployment-'));
 const key='0x'+'44'.repeat(32);const account=new Wallet(key);const built=compile();const data='0x'+built.evm.bytecode.object;
 const artifact={chainId:10143,unsignedTransaction:{chainId:'0x279f',value:'0x0',data},creationBytecodeKeccak256:keccak256(data),sourceSha256:'local-test'};
 const input={key,artifact,directory,url:chain.provider._getConnection().url};
 const script=`import sys,json
sys.path.insert(0,'python')
from eth_account import Account
from registry import MonadTestnetRegistry
from monad_deploy import deploy
p=json.load(sys.stdin)
r=MonadTestnetRegistry({'name':'PortableMemory','version':'0','chainId':10143,'verifyingContract':'0x'+'00'*20},{'rpcUrl':'https://test.invalid'})
r.url=p['url']
original=r.rpc
def rpc(method,params):
 if method=='eth_getBlockByNumber' and params[0]=='finalized':params=['latest',False]
 return original(method,params)
r.rpc=rpc
r.rpc_many=lambda calls:[r.rpc(m,p) for m,p in calls]
broadcast=r.broadcast
def interrupted(intent):raise RuntimeError('INTERRUPTED')
r.broadcast=interrupted
try:deploy(r,Account.from_key(p['key']),p['artifact'],p['directory'],bytes(32),timeout=0)
except RuntimeError:pass
r.broadcast=broadcast
result=deploy(r,Account.from_key(p['key']),p['artifact'],p['directory'],bytes(32))
again=deploy(r,Account.from_key(p['key']),p['artifact'],p['directory'],bytes(32))
assert result['transactionHash']==again['transactionHash']
print(json.dumps(result))`;
 try{
  await chain.provider.send('anvil_setBalance',[account.address,'0x56bc75e2d63100000']);
  const result=JSON.parse(execFileSync('.venv/bin/python',['-c',script],{input:JSON.stringify(input),encoding:'utf8'}));
  assert.equal(result.confirmation,'finalized_rpc_verified');
  assert.equal(await chain.provider.getTransactionCount(account.address),1);
  const registry=new Contract(result.contractAddress,built.abi,chain.provider);
  assert.equal(await registry.acceptedAt('0x'+'00'.repeat(32),0),0n);
 }finally{await chain.close();rmSync(directory,{recursive:true,force:true});}
});

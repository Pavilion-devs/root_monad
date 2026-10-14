import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {Wallet, Interface, keccak256} from 'ethers';
import {buildGenesis, types, creationTransaction, verifyGenesis, verifyStatus, verifyFinalized, signGenesis, walletAccount} from '../frontend/ui/src/wallet.js';

const wallet = Wallet.createRandom(), owner = wallet.address.toLowerCase();
const code = '0x6000';
const settings = {serviceId:'0x'+'11'.repeat(32), providerId:'0x'+'22'.repeat(32),
  runtimeCodeHash:keccak256(code), domain:{name:'PortableMemory',version:'0',chainId:10143,verifyingContract:'0x'+'ab'.repeat(20)}};
async function fixture() {
  const genesis = buildGenesis(settings, owner);
  genesis.signature = await wallet.signTypedData(settings.domain, types, genesis.checkpoint);
  const {from, ...transaction} = creationTransaction(settings, owner, genesis);
  return {genesis, status:'ready', verified:true, projectId:genesis.checkpoint.projectId, owner,
    domain:settings.domain, serviceId:settings.serviceId, transaction:{...transaction,kind:'external_wallet'},
    sequence:'0',checkpointDigest:genesis.checkpoint.controlDigest};
}

test('browser hashes, project ID, signature and calldata match independent Python implementation', async () => {
  const result = await fixture();
  const run = spawnSync('.venv/bin/python', ['-c', `import json,sys
sys.path.insert(0,'python')
from protocol import digest,project_id,recover
from wallet_registry import WalletRegistry
x=json.load(sys.stdin)
class R:
 chain_id=10143
 address=x['domain']['verifyingContract']
g=x['genesis']
assert digest('snapshot',g['snapshot'])==g['control']['snapshotDigest']
assert digest('control',g['control'])==g['checkpoint']['controlDigest']
assert project_id(x['owner'],g['control']['creationNonce'])==x['projectId']
assert recover(x['domain'],'Checkpoint',g['checkpoint'],g['signature'])==x['owner']
assert WalletRegistry(R()).transaction(g,x['owner'])==x['transaction']
print('verified')`], {input:JSON.stringify(result),encoding:'utf8'});
  assert.equal(run.status,0,run.stderr); assert.equal(run.stdout.trim(),'verified');
});

test('a service cannot add grants, replace the owner, or change transaction destination', async () => {
  const result = await fixture(); assert.equal(verifyStatus(settings,owner,result,result.genesis),result);
  for (const change of [r=>r.genesis.control.grants.push({application:owner}),r=>r.owner=Wallet.createRandom().address.toLowerCase(),
    r=>r.transaction.to='0x'+'cd'.repeat(20),r=>r.transaction.value='0x1',r=>r.verified=false]) {
    const bad=structuredClone(result);change(bad);assert.throws(()=>verifyStatus(settings,owner,bad,result.genesis));
  }
  assert.throws(()=>verifyGenesis(settings,Wallet.createRandom().address.toLowerCase(),result.genesis));
});

test('wallet account and network changes block signing; wallet rejection propagates', async () => {
  const genesis=buildGenesis(settings,owner); let mode='good';
  const provider={request:async({method,params})=>{
    if(method==='eth_chainId')return mode==='chain'?'0x1':'0x279f';
    if(method==='eth_accounts')return [mode==='account' ? Wallet.createRandom().address : owner];
    if(method==='eth_getCode')return code;
    if(method==='eth_signTypedData_v4') {
      if(mode==='reject')throw Object.assign(Error('user rejected'),{code:4001});
      const typed=JSON.parse(params[1]); const signature=await wallet.signTypedData(typed.domain,types,typed.message);
      if(mode==='change_after_signature')mode='account';
      return signature;
    }
    throw Error(method);
  }};
  await walletAccount(provider,owner);
  const signed=await signGenesis(provider,settings,owner,genesis);verifyGenesis(settings,owner,signed);
  for(const state of ['chain','account','reject','change_after_signature']){
    mode=state;await assert.rejects(()=>signGenesis(provider,settings,owner,genesis));
  }
});

test('success requires a fresh finalized head, exact event and stable canonical receipt', async () => {
  const result=await fixture();const cp=result.genesis.checkpoint;
  const abi=new Interface(['function heads(bytes32) view returns (address,uint256,bytes32)',
    'function acceptedAt(bytes32,uint256) view returns (uint256)',
    'event Advanced(bytes32 indexed projectId,address indexed owner,uint256 sequence,bytes32 previousDigest,bytes32 controlDigest)']);
  const eventData=abi.encodeEventLog(abi.getEvent('Advanced'),[cp.projectId,owner,0,cp.previousDigest,cp.controlDigest]);
  const block={number:'0xa',hash:'0x'+'55'.repeat(32),timestamp:'0x'+Math.floor(Date.now()/1000).toString(16)};
  const event={...eventData,address:settings.domain.verifyingContract,blockNumber:'0xa',blockHash:block.hash,transactionHash:'0x'+'66'.repeat(32),removed:false};
  const receipt={status:'0x1',to:settings.domain.verifyingContract,blockNumber:'0xa',blockHash:block.hash,transactionHash:event.transactionHash,logs:[event]};
  let mode='good',reads=0;
  const provider={request:async({method,params})=>{
    if(method==='eth_chainId')return '0x279f';
    if(method==='eth_accounts')return [owner];
    if(method==='eth_getCode')return mode==='code'?'0x6001':code;
    if(method==='eth_getBlockByNumber')return mode==='stale'?{...block,timestamp:'0x1'}:block;
    if(method==='eth_call')return params[0].data.startsWith(abi.getFunction('heads').selector)?
      abi.encodeFunctionResult('heads',[owner,0,mode==='head'?'0x'+'77'.repeat(32):cp.controlDigest]):abi.encodeFunctionResult('acceptedAt',[10]);
    if(method==='eth_getLogs')return mode==='event'?[]:[event];
    if(method==='eth_getTransactionReceipt'){
      reads++;if(mode==='reorg'&&reads>1)return null;
      return mode==='receipt'?{...receipt,logs:[]}:receipt;
    }
    throw Error(method);
  }};
  assert.equal((await verifyFinalized(provider,settings,owner,result)).sequence,'0');
  for(const failure of ['code','stale','head','event','receipt','reorg']) {
    mode=failure;reads=0;await assert.rejects(()=>verifyFinalized(provider,settings,owner,result),failure);
  }
});

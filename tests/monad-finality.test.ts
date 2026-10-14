import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {rmSync,writeFileSync} from 'node:fs';
import {Contract,JsonRpcProvider,Wallet} from 'ethers';
import {localChain,deploy,verifyRegistryContext} from '../src/chain.js';
import {setup,startMemory} from './memory-support.js';
import {owner,APP_KEY,OWNER_KEY,signed} from './support.js';
import {call,send,envelope,proposal,checkpointTypes} from '../src/client-wire.js';
const RELAYER='0x'+'44'.repeat(32);

function python(script:string,input:any):Promise<any>{
 return new Promise((resolve,reject)=>{
  const p=spawn('.venv/bin/python',['-c',script]);let output='',error='';
  p.stdout.on('data',d=>output+=d);p.stderr.on('data',d=>error+=d);
  p.on('error',reject);p.on('exit',code=>code===0?resolve(JSON.parse(output)):reject(Error(error)));
  p.stdin.end(JSON.stringify(input));
 });
}

test('Monad adapter on local EVM: pending across restart, finalized recovery and independent clients',{timeout:60000},async()=>{
 const chain=await localChain(10143);const s=await setup();
 let service:Awaited<ReturnType<typeof startMemory>>|undefined;
 let clientProvider:JsonRpcProvider|undefined;
 let finalized:any;let fault='';let receiptReads=0;const tags:string[]=[];
 let genesisMined:any;let genesisPendingChecks=0;let finalizeGenesis=true;
 const upstream=chain.provider._getConnection().url;
 const proxy=createServer(async(req,res)=>{
  try{
   let body='';for await(const part of req)body+=part;
   const parsed=JSON.parse(body);
   async function handle(item:any){
    const {method,params,id}=item;
    if(method==='eth_chainId' && fault==='wrong_chain')return {jsonrpc:'2.0',id,result:'0x1'};
    if(method==='eth_getBlockByNumber'){
     tags.push(params[0]);
     if(params[0]==='finalized'){
      if(genesisMined && finalizeGenesis && ++genesisPendingChecks>3)finalized=genesisMined;
      if(fault==='unavailable')return {jsonrpc:'2.0',id,error:{code:-32000,message:'unavailable'}};
      return {jsonrpc:'2.0',id,result:fault==='stale'?{...finalized,timestamp:'0x1'}:finalized};
     }
    }
    const response=await fetch(upstream,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
    const result=await response.json();
    if(method==='eth_sendRawTransaction' && finalizeGenesis && result.result)genesisMined=await chain.provider.send('eth_getBlockByNumber',['latest',false]);
    if(method==='eth_getTransactionReceipt'){
     receiptReads++;
     if(fault==='changing_receipt' && receiptReads%2===0)result.result=null;
     if(fault==='failed_unfinalized' && result.result && BigInt(result.result.blockNumber)>BigInt(finalized.number))result.result.status='0x0';
    }
    if(method==='eth_getBlockByNumber' && fault==='changed_block' && result.result)result.result.hash='0x'+'ff'.repeat(32);
    if(method==='eth_getLogs' && fault==='missing_event')result.result=[];
    return result;
   }
   const result=Array.isArray(parsed)?await Promise.all(parsed.map(handle)):await handle(parsed);
   res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));
  }catch{res.statusCode=500;res.end('{}');}
 });
 await new Promise<void>(resolve=>proxy.listen(0,'127.0.0.1',resolve));
 const proxyUrl=`http://127.0.0.1:${(proxy.address() as any).port}`;
 try{
  const registry=await deploy(await chain.provider.getSigner());
  const domain={name:'PortableMemory',version:'0',chainId:10143,verifyingContract:await registry.getAddress()};
  const genesis={...await signed(s.startup.genesis.control,domain),snapshot:s.startup.genesis.snapshot};
  finalized=await chain.provider.send('eth_getBlockByNumber',['latest',false]);
  await chain.provider.send('anvil_setBalance',[new Wallet(RELAYER).address,'0x56bc75e2d63100000']);
  const client={...s.client,domain};
  const settings={rpcUrl:'https://test.invalid',testTransportUrl:proxyUrl,maxTransactionFeeWei:'1000000000000000000'};
  const startup={...s.startup,config:{...s.startup.config,domain},genesis,registry:settings,relayerKey:RELAYER};
  const restart={...startup,genesis:undefined};
  service=await startMemory(startup,undefined,'tests/finality-server.py');
  assert.ok(genesisPendingChecks>3,'startup waits for finalized genesis using the persisted intent');finalizeGenesis=false;
  clientProvider=new JsonRpcProvider(proxyUrl,10143,{staticNetwork:true,cacheTimeout:-1});
  const clientRegistry=new Contract(await registry.getAddress(),registry.interface,clientProvider);
  const initial=await call(service.url,client,APP_KEY,'context',{});
  assert.equal(initial.authorityMode,'monad_testnet');
  await verifyRegistryContext(client,initial,clientRegistry);
  const p=proposal(client,APP_KEY,initial.checkpoint.controlDigest,'Keep owner approval across applications.');
  await call(service.url,client,APP_KEY,'proposals',p);
  const review=await call(service.url,client,OWNER_KEY,'prepare',{accept:[p.id],reject:[],grants:null});
  const wire=await envelope(client,OWNER_KEY,initial.checkpoint.controlDigest,'commit',{checkpoint:review.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,review.checkpoint)});
  fault='failed_unfinalized';
  await assert.rejects(send(service.url,wire),/COMMIT_PENDING/);
  await service.stop();service=await startMemory(restart,undefined,'tests/finality-server.py');
  const pending=await python('import json,sqlite3,sys; p=json.load(sys.stdin); print(json.dumps(sqlite3.connect(p["db"]).execute("SELECT status FROM intents WHERE digest=?",(p["digest"],)).fetchone()))',{db:startup.db,digest:review.checkpoint.controlDigest});
  assert.deepEqual(pending,['pending'],'provisional failure cannot poison durable recovery');
  assert.equal((await call(service.url,client,APP_KEY,'context',{})).checkpoint.controlDigest,initial.checkpoint.controlDigest);
  fault='';finalized=await chain.provider.send('eth_getBlockByNumber',['latest',false]);
  const ack=await send(service.url,wire);
  assert.equal(ack.confirmation,'finalized_rpc_verified');
  const saved=await python('import json,sqlite3,sys; sys.path.insert(0,"python"); from storage import Store; p=json.load(sys.stdin); db=sqlite3.connect(p["db"]); obj=db.execute("SELECT object FROM intents WHERE digest=?",(p["digest"],)).fetchone()[0]; print(json.dumps(Store(db,bytes.fromhex(p["key"]),p["project"]).get(obj)["confirmation"]))',{db:startup.db,key:startup.key,project:client.projectId,digest:review.checkpoint.controlDigest});
  assert.equal(saved.kind,'finalized_rpc_verified');assert.equal(saved.transactionHash,ack.transactionHash);
  assert.equal(saved.authorityBlockHash,finalized.hash);
  const current=await call(service.url,client,APP_KEY,'context',{});
  await verifyRegistryContext(client,current,clientRegistry);
  const verified=await python('import json,sys; sys.path.insert(0,"python"); from client import verify; from registry import MonadTestnetRegistry; from urllib.request import Request,urlopen; p=json.load(sys.stdin)\ndef rpc(self,m,a):\n with urlopen(Request(self.settings["testTransportUrl"],json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":a}).encode(),{"Content-Type":"application/json"})) as r: return json.load(r)["result"]\nMonadTestnetRegistry.rpc=rpc\nMonadTestnetRegistry.rpc_many=lambda self,calls:[self.rpc(m,p) for m,p in calls]\nprint(json.dumps(verify(p["config"],p["bundle"])))',{config:{...client,registry:settings},bundle:current});
  assert.equal(verified.checkpoint.controlDigest,current.checkpoint.controlDigest);
  await assert.rejects(verifyRegistryContext(client,initial,clientRegistry),/STALE_CONTEXT/);
  const historical=await call(service.url,client,APP_KEY,'history',{checkpointDigest:initial.checkpoint.controlDigest});
  await verifyRegistryContext(client,historical,clientRegistry,initial.checkpoint.controlDigest);
  assert.equal((await registry.queryFilter(registry.filters.Advanced(client.projectId))).length,2,'restart reuses the original transaction');
  assert.ok(await registry.acceptedAt(client.projectId,0n)>0n);
  assert.ok(await registry.acceptedAt(client.projectId,1n)>await registry.acceptedAt(client.projectId,0n));
  for(const failure of ['wrong_chain','unavailable','stale','changed_block','changing_receipt','missing_event']){
   fault=failure;receiptReads=0;
   await assert.rejects(verifyRegistryContext(client,current,clientRegistry),failure);
   receiptReads=0;
   assert.equal((await fetch(service.url+'/head')).status,503,`batched Python service rejects ${failure}`);
  }
  fault='unavailable';
  assert.equal((await fetch(service.url+'/head')).status,503);
  assert.ok(!tags.includes('latest'),'verification never falls back to latest');
  writeFileSync('results/monad-adapter.json',JSON.stringify({passed:true,environment:'Local Anvil EVM with chain ID 10143 and controlled RPC finality; NOT live Monad',genesisWaitsForFinality:true,pendingAcrossRestart:true,unfinalizedFailureIgnored:true,finalizedRecovery:true,noDuplicateTransaction:true,independentPythonAndTypescriptVerification:true,historicalLookupBySequence:true,failures:['wrong chain','unavailable finalized state','stale finalized tip','changed canonical block','changing receipt','missing event'],limitations:['Trusted RPC, not consensus/light-client proof','This fixture measures local behavior only; live evidence is recorded separately']},null,2)+'\n');
 }finally{
  await service?.stop();clientProvider?.destroy();await chain.close();
  await new Promise<void>(resolve=>proxy.close(()=>resolve()));
  rmSync(s.directory,{recursive:true,force:true});
 }
});

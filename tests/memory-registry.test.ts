import test from 'node:test';
import assert from 'node:assert/strict';
import {rmSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {localChain,deploy,RegistryAdapter,verifyRegistryContext} from '../src/chain.js';
import {call,send,envelope,proposal,checkpointTypes,verifyContext} from '../src/client-wire.js';
import {setup,startMemory,SECOND_KEY} from './memory-support.js';
import {owner,OWNER_KEY,APP_KEY,signed} from './support.js';
// Dedicated throwaway relayer, funded only on this test's local Anvil instance.
const RELAYER='0x'+'44'.repeat(32);

test('persistent registry service: durable intents, crash recovery, conflicts, stale storage and independent clients',{timeout:60000},async()=>{
 const chain=await localChain(); const s=await setup(); let server:Awaited<ReturnType<typeof startMemory>>|undefined;
 try {
  const registry=await deploy(await chain.provider.getSigner());
  const domain={name:'PortableMemory',version:'0',chainId:31337,verifyingContract:await registry.getAddress()};
  const {Wallet}=await import('ethers');
  await chain.provider.send('anvil_setBalance',[new Wallet(RELAYER).address,'0x56bc75e2d63100000']);
  const config={...s.startup.config,domain}; const client={...s.client,domain};
  const registrySettings={rpcUrl:chain.provider._getConnection().url};
  const genesis={...await signed(s.startup.genesis.control,domain),snapshot:s.startup.genesis.snapshot};
  const startup={...s.startup,config,genesis,registry:registrySettings,relayerKey:RELAYER};
  const restart={...startup,genesis:undefined};
  server=await startMemory(startup);
  const initial=await call(server.url,client,APP_KEY,'context',{});
  await verifyRegistryContext(client,initial,registry);
  assert.throws(()=>verifyContext(client,initial),/UNVERIFIED/);
  await server.stop();
  const stalePath=join(s.directory,'stale.sqlite');execFileSync('.venv/bin/python',['-c','import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); a.backup(b); b.close(); a.close()',startup.db,stalePath]);
  server=await startMemory(restart);
  async function prepare(text:string){
   const current=await call(server!.url,client,APP_KEY,'context',{});
   const p=proposal(client,APP_KEY,current.checkpoint.controlDigest,text);
   await call(server!.url,client,APP_KEY,'proposals',p);
   const review=await call(server!.url,client,OWNER_KEY,'prepare',{accept:[p.id],reject:[],grants:null});
   const payload={checkpoint:review.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,review.checkpoint)};
   return {review,payload,wire:await envelope(client,OWNER_KEY,current.checkpoint.controlDigest,'commit',payload)};
  }
  const first=await prepare('Retain project context for 30 days.');
  await server.stop();server=await startMemory(restart,'before');
  await assert.rejects(send(server.url,first.wire));
  await server.stop();
  assert.equal((await registry.heads(client.projectId)).sequence,0n,'no broadcast before crash');
  server=await startMemory(restart);
  const firstAck=await send(server.url,first.wire);
  assert.equal(firstAck.committed,first.review.checkpoint.controlDigest);
  assert.equal((await registry.heads(client.projectId)).sequence,1n);
  const second=await prepare('Use explicit owner review for every decision.');
  await server.stop();server=await startMemory(restart,'after');
  await assert.rejects(send(server.url,second.wire));await server.stop();
  assert.equal((await registry.heads(client.projectId)).sequence,2n,'chain accepted before response was lost');
  server=await startMemory(restart);
  assert.equal((await send(server.url,second.wire)).committed,second.review.checkpoint.controlDigest);
  assert.equal((await send(server.url,first.wire)).committed,first.review.checkpoint.controlDigest,'historical retry acknowledges only the original commit');
  let current=await call(server.url,client,SECOND_KEY,'context',{});
  await verifyRegistryContext(client,current,registry);
  assert.equal(current.records.length,2);
  const python=JSON.parse(execFileSync('.venv/bin/python',['python/client.py'],{encoding:'utf8',input:JSON.stringify({url:server.url,config:{...client,registry:registrySettings},key:SECOND_KEY})}));
  assert.equal(python.checkpoint.controlDigest,current.checkpoint.controlDigest);
  await assert.rejects(verifyRegistryContext(client,initial,registry),/STALE_CONTEXT/);
  // A rolled-back database cannot present an old, correctly signed version as current.
  await assert.rejects(startMemory({...restart,db:stalePath}),/CONTENT_UNAVAILABLE/);
  const logs=await registry.queryFilter(registry.filters.Advanced(client.projectId));
  assert.equal(logs.length,3,'genesis and two approvals; crash retries produced no duplicate update');

  const disguised={...initial,verification:'historical_verified'};
  await assert.rejects(verifyRegistryContext(client,disguised,registry),/UNVERIFIED/);
  const history=await call(server.url,client,SECOND_KEY,'history',{checkpointDigest:initial.checkpoint.controlDigest});
  await verifyRegistryContext(client,history,registry,initial.checkpoint.controlDigest);
  const raceA=await prepare('First owner-reviewed candidate.');
  const raceB=await prepare('Second owner-reviewed candidate.');
  await send(server.url,raceA.wire);
  await assert.rejects(send(server.url,raceB.wire),/BASE_CONFLICT/);
  const cachedRead=await envelope(client,SECOND_KEY,raceA.review.checkpoint.controlDigest,'context',{});
  await send(server.url,cachedRead);
  const remaining=raceA.review.control.grants.filter((g:any)=>g.application!==new Wallet(SECOND_KEY).address.toLowerCase());
  const revoke=await call(server.url,client,OWNER_KEY,'prepare',{accept:[],reject:[],grants:remaining});
  await call(server.url,client,OWNER_KEY,'commit',{checkpoint:revoke.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,revoke.checkpoint)});
  await assert.rejects(send(server.url,cachedRead),/SCOPE_DENIED/);
  await assert.rejects(call(server.url,client,SECOND_KEY,'context',{}),/SCOPE_DENIED/);

  // Two signed approvals race at the same base. Both were durably reviewed locally.
  const loser=await prepare('Losing concurrent proposal.');
  const winner=await prepare('Winning concurrent proposal.');
  await chain.provider.send('evm_setAutomine',[false]);
  await assert.rejects(send(server.url,loser.wire),/COMMIT_PENDING/);
  // Exclude the loser's pending transaction so the independent relayer can win.
  const pending=(await chain.provider.send('eth_getBlockByNumber',['pending',true])).transactions;
  assert.equal(pending.length,1);
  await chain.provider.send('anvil_dropTransaction',[pending[0].hash]);
  await chain.provider.send('evm_setAutomine',[true]);
  const adapter=new RegistryAdapter(registry,domain,owner.address);
  await adapter.commit(winner.review.checkpoint,winner.review.control,winner.payload.signature);
  // Service has prepared content but no signed winner envelope: it must refuse old reads.
  await assert.rejects(call(server.url,client,APP_KEY,'context',{}),/AUTHORITY_UNAVAILABLE/);
  const states=JSON.parse(execFileSync('.venv/bin/python',['-c','import json,sqlite3,sys; print(json.dumps(sqlite3.connect(sys.argv[1]).execute("SELECT status FROM intents WHERE digest=?",(sys.argv[2],)).fetchone()))',startup.db,loser.review.checkpoint.controlDigest],{encoding:'utf8'}));
  assert.deepEqual(states,['conflict']);
  await chain.close();
  await assert.rejects(send(server.url,cachedRead),/AUTHORITY_UNAVAILABLE/);
  assert.equal((await fetch(server.url+'/head')).status,503);
  await server.stop();
  writeFileSync('results/memory-registry.json',JSON.stringify({passed:true,authorityMode:'local_registry',
   durableBeforeBroadcast:true,recoveredAfterChainAcceptance:true,noDuplicateApprovals:true,
   independentPythonAndTypescriptVerification:true,historyCannotMasqueradeAsCurrent:true,revocationBlocksFreshAndCachedReads:true,knownCompetingApprovalRejected:true,staleClientRejected:true,rolledBackStorageRejected:true,
   pendingTransactionNotReportedCommitted:true,competingExternalApprovalWins:true,unknownCurrentContentFailsClosed:true,rpcOutageFailsClosed:true,
   limitations:['Local Anvil inclusion, not Monad finality','Provider import and protected key recovery remain','A dedicated relayer per service is required','RPC is trusted; no light-client proof']},null,2)+'\n');
 } finally {await server?.stop();await chain.close();rmSync(s.directory,{recursive:true,force:true});}
});

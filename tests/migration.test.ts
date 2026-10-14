import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync,spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,rmSync,existsSync,mkdirSync,statSync} from 'node:fs';
import {join} from 'node:path';
import {Wallet} from 'ethers';
import {localChain,deploy,verifyRegistryContext} from '../src/chain.js';
import {setup,startMemory,SECOND_KEY} from './memory-support.js';
import {signed,owner,OWNER_KEY,APP_KEY,bytes} from './support.js';
import {call,send,envelope,proposal,checkpointTypes} from '../src/client-wire.js';

function admin(request:any,expected?:string){
 const r=spawnSync('.venv/bin/python',['python/admin.py'],{input:JSON.stringify(request),encoding:'utf8'});
 const result=JSON.parse(r.stdout||'{}');
 if(expected){assert.equal(result.code,expected);assert.equal(r.status,1);}
 else assert.equal(r.status,0,JSON.stringify(result));
 return result;
}

test('protected archive restores to a new provider; approved handoff survives a crash and fresh clients continue',{timeout:60000},async()=>{
 const chain=await localChain(),s=await setup();let a:Awaited<ReturnType<typeof startMemory>>|undefined,b:typeof a;
 try{
  const registry=await deploy(await chain.provider.getSigner());
  const domain={name:'PortableMemory',version:'0',chainId:31337,verifyingContract:await registry.getAddress()};
  const relayerA='0x'+'44'.repeat(32),relayerB='0x'+'55'.repeat(32);
  for(const key of [relayerA,relayerB])await chain.provider.send('anvil_setBalance',[new Wallet(key).address,'0x56bc75e2d63100000']);
  const config={...s.startup.config,domain},client={...s.client,domain};
  const rpc={rpcUrl:chain.provider._getConnection().url};
  const startA={...s.startup,config,genesis:{...await signed(s.startup.genesis.control,domain),snapshot:s.startup.genesis.snapshot},registry:rpc,relayerKey:relayerA};
  a=await startMemory(startA);
  async function approve(url:string,c:any,text:string,replaces:string|null=null){
   const before=await call(url,c,APP_KEY,'context',{});
   const p=proposal(c,APP_KEY,before.checkpoint.controlDigest,text,replaces);
   await call(url,c,APP_KEY,'proposals',p);
   const review=await call(url,c,OWNER_KEY,'prepare',{accept:[p.id],reject:[],grants:null});
   await call(url,c,OWNER_KEY,'commit',{checkpoint:review.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,review.checkpoint)});
   return await call(url,c,APP_KEY,'context',{});
  }
  const first=await approve(a.url,client,'Retain private project notes for 30 days.');
  const before=await approve(a.url,client,'Retain private project notes for 14 days.',first.records[0].id);
  const pending=proposal(client,APP_KEY,before.checkpoint.controlDigest,'An unapproved suggestion stays a suggestion.');
  await call(a.url,client,APP_KEY,'proposals',pending);
  const oldWire=await envelope(client,APP_KEY,before.checkpoint.controlDigest,'context',{});
  await send(a.url,oldWire);
  mkdirSync(join(s.directory,'owner-keys'));
  const archive=join(s.directory,'recovery.enc'),recoveryKeyFile=join(s.directory,'owner-keys','recovery.key');
  const source={db:startA.db,key:startA.key,config,registry:rpc,relayerKey:relayerA};
  admin({...source,operation:'export',archive,recoveryKeyFile});
  assert.equal(statSync(recoveryKeyFile).mode&0o777,0o600);
  for(const secret of [before.records[0].content,startA.key,OWNER_KEY])assert.ok(!readFileSync(archive).includes(Buffer.from(secret)));
  await assert.rejects(call(a.url,client,APP_KEY,'proposals',proposal(client,APP_KEY,before.checkpoint.controlDigest,'Blocked while frozen.')),/WRITES_FROZEN/);
  assert.equal((await call(a.url,client,APP_KEY,'context',{})).records[0].content,before.records[0].content);
  const recoveryKey=readFileSync(recoveryKeyFile,'utf8').trim();
  const binding={serviceId:bytes('ab'),storage:{providerId:bytes('cd'),locator:'fixture://provider-b/project-memory'}};
  const directory=join(s.directory,'provider-b');
  const restore={operation:'restore',config,registry:rpc,archive,recoveryKey,binding,directory};
  admin({...restore,recoveryKey:'00'.repeat(32)},'INVALID_RECOVERY_PACKAGE');assert.ok(!existsSync(directory));
  const corrupted=join(s.directory,'corrupt.enc');const bad=JSON.parse(readFileSync(archive,'utf8'));bad.ciphertext=(parseInt(bad.ciphertext.slice(0,2),16)^1).toString(16).padStart(2,'0')+bad.ciphertext.slice(2);writeFileSync(corrupted,JSON.stringify(bad));
  admin({...restore,archive:corrupted},'INVALID_RECOVERY_PACKAGE');assert.ok(!existsSync(directory));
  admin({...restore,config:{...config,owner:new Wallet(SECOND_KEY).address.toLowerCase()}},'CONFIG_MISMATCH');
  admin(restore);
  admin(restore,'DESTINATION_EXISTS');
  const target={db:join(directory,'memory.sqlite'),keyEnvelope:join(directory,'project-key.enc'),recoveryKey,config,registry:rpc,relayerKey:relayerB};
  b=await startMemory(target);
  await assert.rejects(call(b.url,client,APP_KEY,'context',{}),/SERVICE_MOVED/);
  await b.stop();
  // Old project key cannot decrypt the replacement provider's re-encrypted objects.
  const rotated=spawnSync('.venv/bin/python',['-c',"import sys,json,sqlite3; sys.path.insert(0,'python'); from storage import Store; r=json.load(sys.stdin); d=sqlite3.connect(r['db']); s=Store(d,bytes.fromhex(r['key']),r['project']); s.get(d.execute('SELECT id FROM objects LIMIT 1').fetchone()[0])"],{input:JSON.stringify({db:target.db,key:startA.key,project:config.projectId}),encoding:'utf8'});
  assert.notEqual(rotated.status,0);assert.match(rotated.stderr,/INTEGRITY_FAILURE/);
  const review=admin({...target,operation:'prepare-migration'});
  assert.equal(review.control.snapshotDigest,before.control.snapshotDigest);
  assert.equal(review.control.serviceId,binding.serviceId);
  assert.deepEqual(review.control.storage,binding.storage);
  assert.deepEqual(review.control.grants,before.control.grants.map((g:any)=>({...g,serviceId:binding.serviceId})));
  const forged={checkpoint:review.checkpoint,signature:await new Wallet(APP_KEY).signTypedData(domain,checkpointTypes,review.checkpoint)};
  admin({...target,operation:'commit-migration',payload:forged},'WRONG_SIGNER');
  // Preparing a replacement does not change the live provider or chain head.
  assert.equal((await call(a.url,client,APP_KEY,'context',{})).checkpoint.controlDigest,before.checkpoint.controlDigest);
  const payload={checkpoint:review.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,review.checkpoint)};
  const crashed=spawnSync('.venv/bin/python',['tests/recovery-crash-admin.py'],{input:JSON.stringify({...target,operation:'commit-migration',payload}),encoding:'utf8'});
  assert.equal(crashed.status,73);
  const ack=admin({...target,operation:'commit-migration',payload});assert.equal(ack.committed,review.checkpoint.controlDigest);
  admin({...target,operation:'commit-migration',payload:{...payload,checkpoint:{...payload.checkpoint,sequence:'999'}}},'CONTENT_MISMATCH');
  // The old service cannot pretend its old context is still current, or resume writes.
  await assert.rejects(send(a.url,oldWire),/CONTENT_UNAVAILABLE|SERVICE_MOVED/);
  const stoppedUrl=a.url;await a.stop();await assert.rejects(fetch(stoppedUrl+'/head'));
  b=await startMemory(target);
  const fresh={...client,serviceId:binding.serviceId};
  await assert.rejects(call(b.url,client,APP_KEY,'context',{}),/WRONG_AUDIENCE/);
  let context=await call(b.url,fresh,SECOND_KEY,'context',{});await verifyRegistryContext(fresh,context,registry);
  assert.equal(context.records[0].content,before.records[0].content);
  const history=await call(b.url,fresh,SECOND_KEY,'history',{checkpointDigest:context.checkpoint.controlDigest});
  await verifyRegistryContext(fresh,history,registry,context.checkpoint.controlDigest);assert.equal(history.records.length,2);
  const inbox=await call(b.url,fresh,OWNER_KEY,'inbox',{});
  assert.equal(inbox.proposals.find((p:any)=>p.proposal.id===pending.id).status,'pending');
  assert.equal(inbox.proposals.find((p:any)=>p.proposal.id===pending.id).stale,true);
  const py=JSON.parse(execFileSync('.venv/bin/python',['python/client.py'],{input:JSON.stringify({url:b.url,config:{...fresh,registry:rpc},key:SECOND_KEY}),encoding:'utf8'}));
  assert.equal(py.checkpoint.controlDigest,context.checkpoint.controlDigest);
  context=await approve(b.url,fresh,'Retain private project notes for 7 days.',context.records[0].id);
  await verifyRegistryContext(fresh,context,registry);assert.equal(context.records[0].content,'Retain private project notes for 7 days.');
  admin({...restore,directory:join(s.directory,'stale-restore')},'STALE_EXPORT');assert.ok(!existsSync(join(s.directory,'stale-restore')));
  const oldData=readFileSync(archive);assert.ok(!oldData.includes(Buffer.from(recoveryKey)));
  writeFileSync('results/migration.json',JSON.stringify({passed:true,authorityMode:'local_registry',encryptedRecoveryArchive:true,separateRecoveryKey:true,
   wrongKeyAndTamperRejected:true,existingDestinationProtected:true,ownerSignatureRequired:true,freshProjectKey:true,
   interruptedHandoffRecovered:true,oldAudienceRejected:true,originalServiceStopped:true,freshPythonAndTypescriptClients:true,
   correctionsAndHistoryPreserved:true,pendingProposalNotPromoted:true,newProposalsAndApprovalsAfterMigration:true,staleExportRejected:true,
   limitations:['Two isolated instances of the same reference provider; not independent provider implementations','Local Anvil; no Monad finality','Recovery key is an owner-held file; OS keychain integration remains','Old provider copies cannot be erased remotely']},null,2)+'\n');
 } finally {await a?.stop();await b?.stop();await chain.close();rmSync(s.directory,{recursive:true,force:true});}
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {rmSync,writeFileSync} from 'node:fs';
import {Wallet} from 'ethers';
import {localChain,deploy} from '../src/chain.js';
import {setup,startMemory,SECOND_KEY} from './memory-support.js';
import {owner,OWNER_KEY,APP_KEY,signed} from './support.js';
import {call,checkpointTypes} from '../src/client-wire.js';

test('planning and coding adapters share verified memory while generated changes remain owner-reviewed',{timeout:60000},async()=>{
 const chain=await localChain(),s=await setup();let server:Awaited<ReturnType<typeof startMemory>>|undefined;
 try{
  const registry=await deploy(await chain.provider.getSigner());
  const domain={name:'PortableMemory',version:'0',chainId:31337,verifyingContract:await registry.getAddress()};
  const relayer='0x'+'44'.repeat(32);await chain.provider.send('anvil_setBalance',[new Wallet(relayer).address,'0x56bc75e2d63100000']);
  const config={...s.startup.config,domain},client={...s.client,domain};
  const rpc={rpcUrl:chain.provider._getConnection().url};
  server=await startMemory({...s.startup,config,genesis:{...await signed(s.startup.genesis.control,domain),snapshot:s.startup.genesis.snapshot},registry:rpc,relayerKey:relayer});
  function assistant(role:string,suggestion:any=null,submit=false,forbiddenContent?:string){
   return JSON.parse(execFileSync('.venv/bin/python',['tests/assistant-fixture.py'],{encoding:'utf8',input:JSON.stringify({
    url:server!.url,config:{...client,registry:rpc},applicationKey:role==='planning'?APP_KEY:SECOND_KEY,role,
    question:role==='planning'?'What should we decide next?':'What should I implement?',suggestion,submit,forbiddenContent})}));
  }
  const suggestion={kind:'decision',content:'Retain project notes for 30 days.',replaces:null};
  const draft=assistant('planning',suggestion);
  assert.equal(draft.suggestion.status,'draft');assert.equal((await call(server.url,client,OWNER_KEY,'inbox',{})).proposals.length,0);
  const planning=assistant('planning',suggestion,true);
  assert.equal(planning.suggestion.status,'pending_owner_review');
  const unaware=assistant('coding',null,false,suggestion.content);assert.deepEqual(unaware.citations,[]);
  async function accept(pid:string){
   const review=await call(server!.url,client,OWNER_KEY,'prepare',{accept:[pid],reject:[],grants:null});
   return call(server!.url,client,OWNER_KEY,'commit',{checkpoint:review.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,review.checkpoint)});
  }
  await accept(planning.suggestion.proposal.id);
  const coding=assistant('coding',{kind:'decision',content:'Retain project notes for 14 days.',replaces:'first'},true);
  assert.equal(coding.advice.status,'model_generated_unverified');
  assert.equal(coding.citations[0].status,'accepted_decision');assert.equal(coding.citations[0].content,suggestion.content);
  assert.equal(coding.citations[0].sources[0].speaker,'Planning assistant');
  assert.equal(coding.citations[0].sources[0].kind,'application_observation');
  assert.equal(coding.suggestion.proposal.records[0].replaces,planning.suggestion.proposal.records[0].id);
  assert.equal((await call(server.url,client,APP_KEY,'context',{})).records[0].content,suggestion.content);
  await accept(coding.suggestion.proposal.id);
  const continued=assistant('planning',null,false,suggestion.content);
  assert.equal(continued.citations[0].content,'Retain project notes for 14 days.');
  const observation=assistant('coding',{kind:'observation',content:'The test suite may need a retention check.',replaces:null},true);
  await accept(observation.suggestion.proposal.id);
  const reads=assistant('planning');
  assert.ok(reads.citations.some((c:any)=>c.status==='accepted_observation'));
  assert.equal(reads.citations.filter((c:any)=>c.status==='accepted_decision').length,1);
  writeFileSync('results/assistants.json',JSON.stringify({passed:true,modelMode:'controlled_fixture',liveModelCalls:0,
   planningAndCodingIdentities:true,verifiedRegistryContext:true,pendingExcludedFromPrompts:true,
   draftsDoNotWrite:true,ownerReviewRequired:true,correctionsSeenOnNextRun:true,sourceReferencesPreserved:true,
   observationsNotLabeledDecisions:true,protocolCredentialsExcludedFromModelPayload:true,
   limitations:['Shared Python adapter implementation with two role profiles','Live Anthropic transport implemented but not called','Generated advice is unverified; citations do not prove entailment']},null,2)+'\n');
 }finally{await server?.stop();await chain.close();rmSync(s.directory,{recursive:true,force:true});}
});

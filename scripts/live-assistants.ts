/** Opt-in, three-call Anthropic check against disposable local memory and Anvil. */
import {spawn} from 'node:child_process';
import {rmSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {Wallet} from 'ethers';
import {setup,startMemory,SECOND_KEY} from '../tests/memory-support.js';
import {owner,OWNER_KEY,APP_KEY,signed} from '../tests/support.js';
import {localChain,deploy,verifyRegistryContext} from '../src/chain.js';
import {call,proposal,checkpointTypes,verifyReview} from '../src/client-wire.js';
const args=process.argv.slice(2);
if(args.length!==3 || args[0]!=='--live' || args[1]!=='--env-file')throw Error('Use --live --env-file <credential-file>');
const report:any={date:new Date().toISOString(),passed:false,modelMode:'live_anthropic',maxCalls:3,maxOutputTokensPerCall:1536,calls:[],checks:{},limitations:['Three sample-data calls; not a quality benchmark','Local Anvil, not live Monad','Owner signatures use disposable fixtures']};
const chain=await localChain(),s=await setup();let server:Awaited<ReturnType<typeof startMemory>>|undefined;
try{
 const registry=await deploy(await chain.provider.getSigner());
 const domain={name:'PortableMemory',version:'0',chainId:31337,verifyingContract:await registry.getAddress()};
 const relayer='0x'+'44'.repeat(32);await chain.provider.send('anvil_setBalance',[new Wallet(relayer).address,'0x56bc75e2d63100000']);
 const config={...s.startup.config,domain},client={...s.client,domain};
 const rpc={rpcUrl:chain.provider._getConnection().url};
 server=await startMemory({...s.startup,config,genesis:{...await signed(s.startup.genesis.control,domain),snapshot:s.startup.genesis.snapshot},registry:rpc,relayerKey:relayer});
 async function accept(p:any){
  const before=await call(server!.url,client,OWNER_KEY,'context',{});
  const review=await call(server!.url,client,OWNER_KEY,'prepare',{accept:[p.id],reject:[],grants:null});
  verifyReview(client,review,before,p,false);
  await call(server!.url,client,OWNER_KEY,'commit',{checkpoint:review.checkpoint,signature:await owner.signTypedData(domain,checkpointTypes,review.checkpoint)});
 }
 const initial=await call(server.url,client,APP_KEY,'context',{});
 const seed=proposal(client,APP_KEY,initial.checkpoint.controlDigest,'Retain project notes for 30 days.');
 await call(server.url,client,APP_KEY,'proposals',seed);await accept(seed);
 const base=await call(server.url,client,APP_KEY,'context',{});
 const observation=proposal(client,APP_KEY,base.checkpoint.controlDigest,'Import latency has not been measured. No latency target has been approved.');
 observation.records[0].kind='observation';await call(server.url,client,APP_KEY,'proposals',observation);await accept(observation);
 const start=await call(server.url,client,APP_KEY,'context',{});
 const pending=proposal(client,APP_KEY,start.checkpoint.controlDigest,'Retain project notes for 90 days.',seed.records[0].id);
 await call(server.url,client,APP_KEY,'proposals',pending);
 async function run(role:string,question:string,submit=false){
  assert.ok(report.calls.length<3,'LIVE_CALL_BUDGET');
  const input={envFile:args[2],url:server!.url,config:{...client,registry:rpc},applicationKey:role==='planning'?APP_KEY:SECOND_KEY,role,question,submit};
  const output=await new Promise<any>((resolve,reject)=>{
   const child=spawn('.venv/bin/python',['scripts/live-assistant.py'],{stdio:['pipe','pipe','pipe']});let stdout='';
   const timer=setTimeout(()=>{child.kill();reject(Error('LIVE_WORKER_TIMEOUT'));},60000);
   child.stdout.on('data',chunk=>{stdout+=chunk.toString();});child.stderr.resume();
   child.once('error',e=>{clearTimeout(timer);reject(e);});
   child.once('exit',()=>{clearTimeout(timer);try{resolve(JSON.parse(stdout));}catch{reject(Error('INVALID_LIVE_WORKER_OUTPUT'));}});
   child.stdin.end(JSON.stringify(input));
  });
  report.calls.push({role,question,...output});writeFileSync('results/live-assistants.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({call:report.calls.length,role,ok:output.ok,code:output.code,model:output.metrics?.model,usage:output.metrics?.usage,elapsedSeconds:output.metrics?.elapsedSeconds}));
  if(!output.ok)throw Error(output.code);
  assert.ok(!JSON.stringify(output.metrics.memorySent).includes('90 days'),'PENDING_LEAK');
  return output.result;
 }
 const planning=await run('planning','Briefly state the accepted retention decision and distinguish the latency observation from a decision. Propose exactly one correction: change retention to 14 days. Cite the current decision, and use replaces to identify it. Keep advice under 120 words.',true);
 assert.equal(planning.suggestion?.status,'pending_owner_review');
 const correction=planning.suggestion.proposal;
 assert.equal(correction.records[0].replaces,seed.records[0].id);assert.equal(correction.records[0].kind,'decision');
 assert.match(correction.records[0].content,/14\s+days/i);
 assert.ok(planning.citations.some((c:any)=>c.recordId===seed.records[0].id));
 report.checks.correctProposalAndCitation=true;
 const codingBefore=await run('coding','What retention rule should the code implement right now? Cite its accepted memory record. Distinguish any unmeasured latency observation from approved requirements. Do not propose changes; use a null suggestion. Keep advice under 120 words.');
 assert.equal(codingBefore.suggestion,null);assert.ok(codingBefore.citations.some((c:any)=>c.recordId===seed.records[0].id));
 assert.match(codingBefore.advice.text,/30/);report.checks.pendingCorrectionNotCurrent=true;
 await accept(correction);
 const current=await call(server.url,client,SECOND_KEY,'context',{});await verifyRegistryContext(client,current,registry);
 assert.ok(!current.records.some((r:any)=>r.id===seed.records[0].id));report.checks.ownerApprovedExactProposal=true;
 const codingAfter=await run('coding','What retention rule should the code implement right now? Cite its accepted memory record. Give one implementation check, without claiming you ran it. Do not propose changes; use a null suggestion. Keep advice under 120 words.');
 assert.equal(codingAfter.suggestion,null);assert.match(codingAfter.advice.text,/14/);
 assert.ok(codingAfter.citations.some((c:any)=>c.recordId===correction.records[0].id));
 assert.ok(!codingAfter.citations.some((c:any)=>c.recordId===seed.records[0].id));
 report.checks.correctionUsedWithCurrentCitation=true;report.checks.pendingExcludedFromAllPrompts=true;
 report.passed=true;
}catch(error){report.error=error instanceof Error?error.message:'LIVE_CHECK_FAILED';process.exitCode=1;}
finally{
 writeFileSync('results/live-assistants.json',JSON.stringify(report,null,2)+'\n');
 await server?.stop();await chain.close();rmSync(s.directory,{recursive:true,force:true});
 console.log(JSON.stringify({passed:report.passed,calls:report.calls.length,error:report.error,report:'results/live-assistants.json'}));
}

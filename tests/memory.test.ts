import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync,readdirSync,rmSync,writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { call,send,envelope,proposal,verifyContext,verifyContents,verifyReview,checkpointTypes } from '../src/client-wire.js';
import { owner,OWNER_KEY,APP_KEY } from './support.js';
import { setup,startMemory,SECOND_KEY } from './memory-support.js';

test('signed HTTP memory flow survives restart and shares approved corrections with an independent Python client',async()=>{
 const s=await setup(); let server=await startMemory(s.startup);
 const content='Retain project notes for 30 days. Test marker f9c240.';
 const correction='Retain project notes for 14 days. Test marker 26f59a.';
 try {
  const initial=verifyContext(s.client,await call(server.url,s.client,APP_KEY,'context',{}));
  assert.equal(initial.records.length,0);
  const p=proposal(s.client,APP_KEY,initial.checkpoint.controlDigest,content);
  const wire=await envelope(s.client,APP_KEY,initial.checkpoint.controlDigest,'proposals',p);
  const receipt=await send(server.url,wire);assert.equal(receipt.status,'pending');
  assert.equal((await call(server.url,s.client,SECOND_KEY,'context',{})).records.length,0);
  const review=await call(server.url,s.client,OWNER_KEY,'prepare',{accept:[p.id],reject:[],grants:null});
  verifyReview(s.client,review,initial,p,false);
  const misleading=structuredClone(p);misleading.records[0].content='Different text shown to owner';
  assert.throws(()=>verifyReview(s.client,review,initial,misleading,false),/UNEXPECTED_REVIEW_CHANGE/);
  const payload={checkpoint:review.checkpoint,signature:await owner.signTypedData(s.client.domain,checkpointTypes,review.checkpoint)};
  await assert.rejects(call(server.url,s.client,APP_KEY,'commit',payload),/SCOPE_DENIED/);
  const commitWire=await envelope(s.client,OWNER_KEY,initial.checkpoint.controlDigest,'commit',payload);
  await send(server.url,commitWire);
  const accepted=verifyContext(s.client,await call(server.url,s.client,SECOND_KEY,'context',{}));
  assert.equal(accepted.records[0].content,content);
  function pythonRead(){return JSON.parse(execFileSync('.venv/bin/python',['python/client.py'],{input:JSON.stringify({url:server.url,config:s.client,key:SECOND_KEY}),encoding:'utf8'}));}
  assert.equal(pythonRead().records[0].content,content);
  const stale=proposal(s.client,APP_KEY,initial.checkpoint.controlDigest,'Stale proposal');
  await assert.rejects(call(server.url,s.client,APP_KEY,'proposals',stale),/BASE_CONFLICT/);
  const corrected=proposal(s.client,SECOND_KEY,accepted.checkpoint.controlDigest,correction,accepted.records[0].id);
  await call(server.url,s.client,SECOND_KEY,'proposals',corrected);
  const competing=proposal(s.client,APP_KEY,accepted.checkpoint.controlDigest,'Keep for 90 days.',accepted.records[0].id);
  await call(server.url,s.client,APP_KEY,'proposals',competing);
  await assert.rejects(call(server.url,s.client,OWNER_KEY,'prepare',{accept:[corrected.id,competing.id],reject:[],grants:null}),/INVALID_TRANSITION/);
  const fix=await call(server.url,s.client,OWNER_KEY,'prepare',{accept:[corrected.id],reject:[competing.id],grants:null});
  verifyContents(s.client,{...fix,verification:'historical_verified'});
  await call(server.url,s.client,OWNER_KEY,'commit',{checkpoint:fix.checkpoint,signature:await owner.signTypedData(s.client.domain,checkpointTypes,fix.checkpoint)});
  assert.equal(pythonRead().records[0].content,correction);
  const current=verifyContext(s.client,await call(server.url,s.client,APP_KEY,'context',{}));
  assert.equal(current.records.length,1);assert.equal(current.records[0].content,correction);
  const tampered=structuredClone(current);tampered.records[0].content='Unapproved substitution';
  assert.throws(()=>verifyContext(s.client,tampered),/CONTENT_MISMATCH/);
  const omitted=structuredClone(current);omitted.sources=[];
  assert.throws(()=>verifyContext(s.client,omitted),/INCOMPLETE_SOURCES/);
  const history=verifyContext(s.client,await call(server.url,s.client,SECOND_KEY,'history',{checkpointDigest:current.checkpoint.controlDigest}));
  assert.equal(history.records.length,2);assert.ok(history.records.some((r:any)=>r.content===content));
  await server.stop(); server=await startMemory({...s.startup,genesis:undefined});
  assert.equal(pythonRead().records[0].content,correction);
  assert.equal((await send(server.url,commitWire)).committed,review.checkpoint.controlDigest);
  const result=await call(server.url,s.client,OWNER_KEY,'inbox',{});
  assert.equal(result.proposals.length,3);
  assert.equal(result.proposals.filter((p:any)=>p.status==='rejected').length,1);
  for(const name of readdirSync(s.directory)){
   const bytes=readFileSync(join(s.directory,name));
   assert.ok(!bytes.includes(Buffer.from(content)) && !bytes.includes(Buffer.from(correction)),`plaintext in ${name}`);
   assert.ok(!bytes.includes(Buffer.from(s.startup.key)),'key stored in plaintext');
  }
  const bad=await fetch(server.url+`/v0/projects/${s.client.projectId}/context`,{method:'POST',headers:{'Origin':'https://untrusted.example','Content-Type':'application/json'},body:'{}'});
  assert.equal(bad.status,403);
  writeFileSync('results/memory-flow.json',JSON.stringify({passed:true,authorityMode:'signed_log',
   pendingNotCurrent:true,appCannotApprove:true,pythonAndTypescriptReadSameDecision:true,correctionPreservesHistory:true,
   conflictingCorrectionsRejected:true,staleWriteRejected:true,serviceRestart:true,durableCommitRetry:true,
   databasePlaintextScanPassed:true,clientTamperingAndOmissionChecks:true,originDenied:true,
   limitations:['This scenario uses signed-log authority; registry mode has a separate integration test','Synthetic data; no model calls','Recovery key remains in test launcher memory','No provider migration in this test']},null,2)+'\n');
 } finally {await server.stop();rmSync(s.directory,{recursive:true,force:true});}
});

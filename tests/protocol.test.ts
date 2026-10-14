import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { verifyTypedData } from 'ethers';
import { strictParse,canonical,digest,validate,verifyOwner,SignedLog,RequestGate,TYPES,checkSignature } from '../src/protocol.js';
import { owner,app,control,signed,bytes,baselineDomain,NOW,project } from './support.js';
const vector=JSON.parse(readFileSync('fixtures/authority-vector.json','utf8'));

test('Python and TypeScript agree on bytes, project identity, digests and signatures in both directions',() => {
  const result=JSON.parse(execFileSync('.venv/bin/python',['python/protocol.py'],{input:JSON.stringify(vector),encoding:'utf8'}));
  assert.equal(result.projectId,project);
  assert.equal(result.canonical,canonical(vector.control));
  assert.equal(result.controlDigest,digest('control',vector.control));
  assert.equal(result.requestDigest,digest('request',vector.requestBody));
  assert.equal(result.checkpointSigner,vector.owner);
  assert.equal(result.requestSigner,vector.app);
  assert.equal(verifyTypedData(vector.domain,{Checkpoint:TYPES.Checkpoint},vector.checkpoint,result.checkpointSignature).toLowerCase(),vector.owner);
  assert.equal(verifyTypedData(vector.domain,{Request:TYPES.Request},vector.requestAuth,result.requestSignature).toLowerCase(),vector.app);
  writeFileSync('results/cross-language.json',JSON.stringify({passed:true,projectId:project,controlDigest:result.controlDigest,
    requestDigest:result.requestDigest,checkpointVerifiedBothDirections:true,requestVerifiedBothDirections:true},null,2)+'\n');
});

test('canonical JSON rejects duplicate keys, malformed Unicode and unsafe numbers',() => {
  for (const raw of ['{"a":1,"a":2}','{"a":{"b":1,"b":2}}','{"a":"\\ud800"}','{"a":1e999}','{"a":9007199254740992}','{"a":1,}'])
    assert.throws(() => strictParse(raw));
  assert.equal(canonical(strictParse('{"b":0.5,"a":"😀"}')),'{"a":"😀","b":0.5}');
  assert.equal(canonical({'\ufb33':1,'😀':2}),'{'+'"😀":2,"דּ":1}');
});

test('schemas reject authority labels, noncanonical counters, overflow and ambiguous grant sets',() => {
  const cases=[{...control(),owner_confirmed:true},{...control(),sequence:'01'},
    {...control(),sequence:String(1n<<256n)}, {...control(),grants:[...control().grants,...control().grants]},
    {...control(),grants:[{...control().grants[0],rights:['read_current','propose']}]},
    {...control(),grants:[{...control().grants[0],serviceId:bytes('ab')}]}];
  cases.forEach(body => assert.throws(() => validate('control',body)));
});

test('signed log rejects changed payload, wrong signer/domain, replay, skipped revision and expiry',async () => {
  const c0=await signed(control()); const log=new SignedLog(owner.address,baselineDomain);
  assert.throws(() => log.append(c0.checkpoint,{...c0.control,salt:bytes('aa')},c0.signature,NOW),/CONTENT_MISMATCH/);
  const wrong=await signed(control(),baselineDomain, '4102444800',app);
  assert.throws(() => log.append(wrong.checkpoint,wrong.control,wrong.signature,NOW),/WRONG_SIGNER/);
  assert.throws(() => verifyOwner({...baselineDomain,salt:bytes('ab')},c0.checkpoint,c0.control,c0.signature,owner.address),/WRONG_SIGNER/);
  assert.throws(() => log.append(c0.checkpoint,c0.control,c0.signature,4_102_444_801n),/EXPIRED/);
  log.append(c0.checkpoint,c0.control,c0.signature,NOW);
  assert.throws(() => log.append(c0.checkpoint,c0.control,c0.signature,NOW),/BASE_CONFLICT/);
  const skip=await signed(control('2',c0.checkpoint.controlDigest));
  assert.throws(() => log.append(skip.checkpoint,skip.control,skip.signature,NOW),/BASE_CONFLICT/);
  const copy=log.export(); copy[0].control.salt=bytes('ff');
  assert.notEqual(copy[0].control.salt,log.head!.control.salt);
});

test('two independent signed log replicas accept different valid successors',async () => {
  const a=new SignedLog(owner.address,baselineDomain), b=new SignedLog(owner.address,baselineDomain);
  const c0=await signed(control());
  for (const log of [a,b]) log.append(c0.checkpoint,c0.control,c0.signature,NOW);
  const left=await signed(control('1',c0.checkpoint.controlDigest,'aa'));
  const right=await signed(control('1',c0.checkpoint.controlDigest,'bb'));
  a.append(left.checkpoint,left.control,left.signature,NOW); b.append(right.checkpoint,right.control,right.signature,NOW);
  assert.notEqual(a.head!.checkpoint.controlDigest,b.head!.checkpoint.controlDigest);
  assert.throws(() => a.append(right.checkpoint,right.control,right.signature,NOW),/BASE_CONFLICT/);
  const restored=SignedLog.fromHistory(owner.address,baselineDomain,JSON.parse(JSON.stringify(a.export())));
  assert.deepEqual(restored.head,a.head);
  const tampered=a.export(); tampered[1].control.salt=bytes('cc');
  assert.throws(() => SignedLog.fromHistory(owner.address,baselineDomain,tampered),/CONTENT_MISMATCH/);
  writeFileSync('results/signed-log.json',JSON.stringify({passed:true,replicasDiverged:true,
    leftDigest:a.head!.checkpoint.controlDigest,rightDigest:b.head!.checkpoint.controlDigest,
    historyRestored:true,limitation:'Historical signatures do not prove latest state or initial receipt time.'},null,2)+'\n');
});

test('signature representation rejects malleable and truncated signatures',() => {
  checkSignature(vector.checkpointSignature);
  const sig=vector.checkpointSignature;
  const order=0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
  const highS=(order-BigInt('0x'+sig.slice(66,130))).toString(16).padStart(64,'0');
  for (const bad of [sig.slice(0,-2),sig.slice(0,66)+highS+sig.slice(130),'0x'+'00'.repeat(65)])
    assert.throws(() => checkSignature(bad),/INVALID_SIGNATURE/);
});

test('request gate binds payload, project, service, current checkpoint and scope; retries do not rerun',async () => {
  const gate=new RequestGate(baselineDomain); let calls=0;
  const {requestAuth:auth,requestBody:body,requestSignature:signature}=vector;
  const run=(c=control(),a=auth,b=body,s=signature) => gate.execute(c,a,b,s,NOW,() => ({calls:++calls}));
  assert.deepEqual(run(),{calls:1}); assert.deepEqual(run(),{calls:1}); assert.equal(calls,1);
  assert.throws(() => run(control(),auth,{...body,payload:{query:'Changed'}}),/CONTENT_MISMATCH/);
  assert.throws(() => run(control(),{...auth,serviceId:bytes('aa')}),/WRONG_AUDIENCE/);
  assert.throws(() => run(control(),{...auth,projectId:bytes('aa')}),/WRONG_AUDIENCE/);
  assert.throws(() => run(control(),{...auth,deadline:String(NOW+301n)}),/EXPIRED_REQUEST/);
  const changedAuth={...auth,deadline:String(NOW+61n)};
  const changedSig=await app.signTypedData(baselineDomain,{Request:TYPES.Request},changedAuth);
  assert.throws(() => run(control(),changedAuth,body,changedSig),/REPLAY_MISMATCH/);
  const history={...body,path:`/v0/projects/${project}/history`,operation:'history'};
  const historyAuth={...auth,nonce:bytes('ab'),requestDigest:digest('request',history)};
  const historySig=await app.signTypedData(baselineDomain,{Request:TYPES.Request},historyAuth);
  assert.throws(() => run(control(),historyAuth,history,historySig),/SCOPE_DENIED/);
  const revoked={...control('1',auth.checkpointDigest,'aa'),grants:[]};
  assert.throws(() => run(revoked),/BASE_CONFLICT/);
  const fresh={...auth,checkpointDigest:digest('control',revoked),nonce:bytes('ac')};
  const freshSig=await app.signTypedData(baselineDomain,{Request:TYPES.Request},fresh);
  assert.throws(() => run(revoked,fresh,body,freshSig),/SCOPE_DENIED/);
  assert.equal(calls,1);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { Contract, JsonRpcProvider } from 'ethers';
import { localChain,deploy,RegistryAdapter } from '../src/chain.js';
import { owner,app,control,signed,bytes,nonce,OWNER_KEY,baselineDomain } from './support.js';
import { digest,TYPES,RequestGate,type RequestBody } from '../src/protocol.js';

test('local registry orders competing updates and enforces its actual trust boundary',async t => {
  const chain=await localChain();
  const outcomes:Record<string,unknown>={environment:'Anvil local EVM, chain 31337; not Monad',compiler:'solc 0.8.36',checks:{}};
  const passed=(name:string,value:unknown=true) => {(outcomes.checks as Record<string,unknown>)[name]=value;};
  try {
    const registry=await deploy(await chain.provider.getSigner(0));
    const address=await registry.getAddress();
    const domain={name:'PortableMemory',version:'0',chainId:31337,verifyingContract:address};
    const adapter=new RegistryAdapter(registry,domain,owner.address);
    const c0=await signed(control(),domain);
    await t.test('genesis cannot be claimed by another owner or created without owner approval',async () => {
      await assert.rejects(registry.create.staticCall(app.address,nonce,c0.checkpoint,c0.signature),/InvalidGenesis/);
      const wrong=await signed(control(),domain,'4102444800',app);
      await assert.rejects(registry.create.staticCall(owner.address,nonce,wrong.checkpoint,wrong.signature),/WrongSigner/);
      passed('genesisOwnership');
    });
    await t.test('create binds project derivation and accepts relayed owner signatures',async () => {
      const created=await adapter.commit(c0.checkpoint,c0.control,c0.signature);
      assert.equal((await adapter.head(c0.checkpoint.projectId)).digest,c0.checkpoint.controlDigest);
      outcomes.genesisGas=created.gasUsed;
      await assert.rejects(registry.create.staticCall(owner.address,nonce,c0.checkpoint,c0.signature),/AlreadyExists/);
      passed('genesis');
    });
    const left=await signed(control('1',c0.checkpoint.controlDigest,'aa'),domain);
    const right=await signed(control('1',c0.checkpoint.controlDigest,'bb'),domain);
    await t.test('changed digest, wrong key, wrong chain, wrong contract and baseline signatures fail',async () => {
      await assert.rejects(registry.advance.staticCall({...left.checkpoint,controlDigest:bytes('cc')},left.signature),/WrongSigner/);
      for (const d of [{...domain,chainId:31338},{...domain,verifyingContract:'0x'+'ab'.repeat(20)},baselineDomain]) {
        const bad=await signed(left.control,d);
        await assert.rejects(registry.advance.staticCall(bad.checkpoint,bad.signature),/WrongSigner/);
      }
      const wrong=await signed(left.control,domain,'4102444800',app);
      await assert.rejects(registry.advance.staticCall(wrong.checkpoint,wrong.signature),/WrongSigner/);
      passed('signatureBinding');
    });
    await t.test('expired, zero and skipped checkpoints fail',async () => {
      const expired=await signed(left.control,domain,'1');
      await assert.rejects(registry.advance.staticCall(expired.checkpoint,expired.signature),/Expired/);
      const skipped=await signed({...left.control,sequence:'2'},domain);
      await assert.rejects(registry.advance.staticCall(skipped.checkpoint,skipped.signature),/BaseConflict/);
      const zero={...left.checkpoint,controlDigest:bytes('00')};
      const sig=await owner.signTypedData(domain,{Checkpoint:TYPES.Checkpoint},zero);
      await assert.rejects(registry.advance.staticCall(zero,sig),/InvalidDigest/);
      passed('expiryAndSequence');
    });
    await t.test('Python-signed winner advances; competing successor and replay fail in the EVM',async () => {
      const signature=execFileSync('.venv/bin/python',['-c',
        'import sys,json; sys.path.insert(0,"python"); from protocol import sign; p=json.load(sys.stdin); print(sign(p["key"],p["domain"],"Checkpoint",p["body"]))'],
        {input:JSON.stringify({key:OWNER_KEY,domain,body:left.checkpoint}),encoding:'utf8'}).trim();
      const applied=await adapter.commit(left.checkpoint,left.control,signature);
      outcomes.updateGas=applied.gasUsed;
      await assert.rejects(registry.advance.staticCall(right.checkpoint,right.signature),/BaseConflict/);
      await assert.rejects(registry.advance.staticCall(left.checkpoint,left.signature),/BaseConflict/);
      assert.equal((await adapter.head(c0.checkpoint.projectId)).digest,left.checkpoint.controlDigest);
      passed('singleWinner'); passed('pythonSignatureOnEvm');
    });
    await t.test('lost acknowledgement retry recognizes committed checkpoint without a second transaction',async () => {
      const before=await chain.provider.getBlockNumber();
      assert.equal((await adapter.commit(left.checkpoint,left.control,left.signature)).status,'already_applied');
      assert.equal(await chain.provider.getBlockNumber(),before);
      passed('idempotentRetry');
    });
    await t.test('separate client connection detects a valid but stale provider history',async () => {
      const url=chain.provider._getConnection().url;
      const otherProvider=new JsonRpcProvider(url,31337,{staticNetwork:true,cacheTimeout:-1});
      try {
        const otherRegistry=new Contract(address,registry.interface,otherProvider);
        const observed=await otherRegistry.heads(c0.checkpoint.projectId);
        assert.equal(observed.digest,left.checkpoint.controlDigest);
        assert.notEqual(observed.digest,c0.checkpoint.controlDigest);
        passed('staleProviderDetected');
      } finally {otherProvider.destroy();}
    });
    await t.test('missing or tampered content fails instead of serving old context',async () => {
      await assert.rejects(adapter.verifiedControl(c0.checkpoint.projectId,() => {throw Error('CONTENT_UNAVAILABLE');}),/CONTENT_UNAVAILABLE/);
      await assert.rejects(adapter.verifiedControl(c0.checkpoint.projectId,() => c0.control),/INTEGRITY_FAILURE/);
      assert.deepEqual(await adapter.verifiedControl(c0.checkpoint.projectId,() => left.control),left.control);
      passed('storageFailure');
    });
    await t.test('offchain gate refuses revoked app and cached-result replay after a confirmed control change',async () => {
      const gate=new RequestGate(domain); let calls=0;
      const body:RequestBody={formatVersion:'0',projectId:c0.checkpoint.projectId,method:'POST',
        path:`/v0/projects/${c0.checkpoint.projectId}/context`,operation:'context',payload:{}};
      const now=BigInt((await chain.provider.getBlock('latest'))!.timestamp);
      const auth={projectId:body.projectId,serviceId:left.control.serviceId,checkpointDigest:left.checkpoint.controlDigest,
        requestDigest:digest('request',body),nonce:bytes('dd'),deadline:String(now+120n)};
      const signature=await app.signTypedData(domain,{Request:TYPES.Request},auth);
      gate.execute(left.control,auth,body,signature,now,() => ++calls);
      const revoked=await signed({...control('2',left.checkpoint.controlDigest,'cc'),grants:[]},domain);
      await adapter.commit(revoked.checkpoint,revoked.control,revoked.signature);
      const current=await adapter.verifiedControl(body.projectId,() => revoked.control);
      assert.throws(() => gate.execute(current,auth,body,signature,now,() => ++calls),/BASE_CONFLICT/);
      const fresh={...auth,checkpointDigest:revoked.checkpoint.controlDigest,nonce:bytes('ee')};
      const freshSig=await app.signTypedData(domain,{Request:TYPES.Request},fresh);
      assert.throws(() => gate.execute(current,fresh,body,freshSig,now,() => ++calls),/SCOPE_DENIED/);
      assert.equal(calls,1); passed('revocationAtOffchainBoundary');
    });
    outcomes.passed=true;
    outcomes.limitations=['No live Monad measurements','Registry does not enforce private grants','Request nonce cache is in-memory in this experiment',
      'No encryption/storage service implemented','Baseline replicas diverge without a common sequencer; a trusted sequencer is a valid alternative'];
    writeFileSync('results/authority-comparison.json',JSON.stringify(outcomes,null,2)+'\n');
  } finally {await chain.close();}
});

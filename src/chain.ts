import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { isDeepStrictEqual } from 'node:util';
import { setTimeout as delay } from 'node:timers/promises';
import { Contract, ContractFactory, JsonRpcProvider, type Signer } from 'ethers';
import { verifyOwner, type Checkpoint, type Control } from './protocol.js';
const require = createRequire(import.meta.url);
const solc = require('solc');
export function compile() {
  const input = {language:'Solidity',sources:{'MemoryRegistry.sol':{content:readFileSync(new URL('../contracts/MemoryRegistry.sol',import.meta.url),'utf8')}},
    settings:{evmVersion:'cancun',optimizer:{enabled:true,runs:200},outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
  const output = JSON.parse(solc.compile(JSON.stringify(input),{import:(name:string) => {
    try {return {contents:readFileSync(require.resolve(name),'utf8')};} catch {return {error:`Unresolved import ${name}`};}
  }}));
  const errors = (output.errors ?? []).filter((e:any) => e.severity === 'error');
  if (errors.length) throw Error(JSON.stringify(errors));
  return output.contracts['MemoryRegistry.sol'].MemoryRegistry;
}
export async function localChain(chainId:31337|10143=31337) {
  const listener = createServer();
  await new Promise<void>(resolve => listener.listen(0,'127.0.0.1',resolve));
  const port = (listener.address() as {port:number}).port;
  await new Promise<void>((resolve,reject) => listener.close(e => e ? reject(e) : resolve()));
  // Anvil test accounts only; no real wallet or external RPC is used.
  const child = spawn('anvil',['--host','127.0.0.1','--port',String(port),'--chain-id',String(chainId),'--hardfork','cancun','--silent'],{stdio:'ignore'});
  let spawnError: Error | undefined;
  child.on('error',e => {spawnError=e;});
  const provider = new JsonRpcProvider(`http://127.0.0.1:${port}`,chainId,{staticNetwork:true,cacheTimeout:-1});
  provider.pollingInterval = 50;
  const close = async () => {
    provider.destroy();
    if (child.exitCode === null && child.signalCode === null) {
      await new Promise<void>(resolve => {child.once('exit',() => resolve()); child.kill('SIGTERM');});
    }
  };
  for (let n=0;n<100;n++) {
    if (spawnError || child.exitCode !== null) {provider.destroy(); throw spawnError ?? Error('ANVIL_EXITED');}
    try {await provider.getBlockNumber(); return {provider,close};} catch {await delay(50);}
  }
  await close(); throw Error('ANVIL_START_TIMEOUT');
}
export async function deploy(signer: Signer) {
  const built=compile();
  const deployment=await new ContractFactory(built.abi,built.evm.bytecode.object,signer).deploy();
  await deployment.waitForDeployment();
  return new Contract(await deployment.getAddress(),built.abi,signer);
}

/** Test adapter. Anvil inclusion is local evidence, not Monad finality. */
export class RegistryAdapter {
  constructor(readonly registry: Contract, readonly domain: any, readonly owner: string) {}
  async head(projectId: string) {
    const h=await this.registry.heads(projectId);
    return {owner:h.owner.toLowerCase(),sequence:h.sequence.toString(),digest:h.digest};
  }
  async commit(cp: Checkpoint, control: Control, signature: string) {
    verifyOwner(this.domain,cp,control,signature,this.owner);
    const head=await this.head(cp.projectId);
    if (head.owner===this.owner.toLowerCase() && head.sequence===cp.sequence && head.digest===cp.controlDigest)
      return {status:'already_applied',gasUsed:null};
    const tx=cp.sequence==='0'
      ? await this.registry.create(this.owner,control.creationNonce,cp,signature)
      : await this.registry.advance(cp,signature);
    const receipt=await tx.wait();
    const confirmed=await this.registry.heads(cp.projectId,{blockTag:receipt.blockNumber});
    if (confirmed.digest!==cp.controlDigest) throw Error('CONFIRMATION_MISMATCH');
    return {status:'applied',gasUsed:receipt.gasUsed.toString()};
  }
  async verifiedControl(projectId: string, load:(digest:string)=>Control) {
    const head=await this.head(projectId);
    const control=load(head.digest);
    const {digest}=await import('./protocol.js');
    if (control.projectId!==projectId || control.sequence!==head.sequence || digest('control',control)!==head.digest) throw Error('INTEGRITY_FAILURE');
    return control;
  }
}

/** Independent client check against its own pinned registry connection. */
export async function verifyRegistryContext(config: import('./client-wire.js').ClientConfig, bundle:any, registry:Contract, historicalDigest?:string) {
  const {verifyContents,checkpointTypes}=await import('./client-wire.js');
  const {verifyTypedData}=await import('ethers');
  if(config.domain.name!=='PortableMemory' || config.domain.version!=='0' || Object.keys(config.domain).sort().join(',')!=='chainId,name,verifyingContract,version')throw Error('WRONG_REGISTRY');
  const expected=historicalDigest?'historical_verified':'current_verified';
  const chainId=BigInt(config.domain.chainId);
  const monad=chainId===10143n;
  if(chainId!==31337n && !monad)throw Error('WRONG_REGISTRY');
  if(bundle.authorityMode!==(monad?'monad_testnet':'local_registry') || bundle.verification!==expected || (historicalDigest && bundle.checkpoint.controlDigest!==historicalDigest))throw Error('UNVERIFIED');
  const provider=registry.runner?.provider;
  if(!provider || (await provider.getNetwork()).chainId!==chainId ||
    (await registry.getAddress()).toLowerCase()!==config.domain.verifyingContract.toLowerCase())throw Error('WRONG_REGISTRY');
  verifyContents(config,bundle);
  const cp=bundle.checkpoint;
  if(verifyTypedData(config.domain,checkpointTypes,cp,bundle.signature).toLowerCase()!==config.owner.toLowerCase())throw Error('WRONG_SIGNER');
  if(monad) {
    // Raw RPC reads bypass provider caches when rechecking finality evidence.
    const rpc=(method:string,params:any[]) => (provider as JsonRpcProvider).send(method,params);
    if(BigInt(await rpc('eth_chainId',[]))!==chainId)throw Error('WRONG_REGISTRY');
    const block=await rpc('eth_getBlockByNumber',['finalized',false]);
    const age=Date.now()/1000-Number(BigInt(block?.timestamp??'0x0'));
    if(!block?.hash || !block?.number || age>120 || age < -30)throw Error('AUTHORITY_UNAVAILABLE');
    const address=await registry.getAddress();
    if(await rpc('eth_getCode',[address,block.number])==='0x')throw Error('REGISTRY_MISSING');
    const at=async (name:string,args:any[]) => registry.interface.decodeFunctionResult(name,await rpc('eth_call',[{to:address,data:registry.interface.encodeFunctionData(name,args)},block.number]));
    const head=await at('heads',[config.projectId]);
    if(head.owner.toLowerCase()!==config.owner.toLowerCase())throw Error('WRONG_SIGNER');
    if(!historicalDigest && (head.digest!==cp.controlDigest || head.sequence.toString()!==cp.sequence))throw Error('STALE_CONTEXT');
    const [height]=await at('acceptedAt',[config.projectId,cp.sequence]);
    if(height===0n || height>BigInt(block.number))throw Error('UNVERIFIED');
    const tag='0x'+height.toString(16);
    const topics=registry.interface.encodeFilterTopics('Advanced',[config.projectId,config.owner]);
    const logs=await rpc('eth_getLogs',[{address,fromBlock:tag,toBlock:tag,topics}]);
    const matches=logs.filter((log:any) => {
      if(log.removed || log.address?.toLowerCase()!==address.toLowerCase() || BigInt(log.blockNumber)!==height || JSON.stringify(log.topics)!==JSON.stringify(topics))throw Error('UNVERIFIED');
      const args=registry.interface.parseLog(log)?.args;
      return args && args.sequence.toString()===cp.sequence && args.previousDigest===cp.previousDigest && args.controlDigest===cp.controlDigest;
    });
    if(matches.length!==1)throw Error('UNVERIFIED');
    const event=matches[0];
    const receipt=await rpc('eth_getTransactionReceipt',[event.transactionHash]);
    if(!receipt || receipt.status!=='0x1' || receipt.transactionHash!==event.transactionHash || receipt.to?.toLowerCase()!==address.toLowerCase() || receipt.blockNumber!==event.blockNumber || receipt.blockHash!==event.blockHash || !receipt.logs.some((log:any)=>isDeepStrictEqual(log,event)))throw Error('UNVERIFIED');
    const canonical=await rpc('eth_getBlockByNumber',[tag,false]);
    const second=await rpc('eth_getTransactionReceipt',[event.transactionHash]);
    const sameView=await rpc('eth_getBlockByNumber',[block.number,false]);
    if(canonical?.hash!==receipt.blockHash || !isDeepStrictEqual(second,receipt) || sameView?.hash!==block.hash)throw Error('AUTHORITY_UNAVAILABLE');
    return bundle;
  }
  const block=await provider.getBlock('latest'); if(!block)throw Error('AUTHORITY_UNAVAILABLE');
  const head=await registry.heads(config.projectId,{blockTag:block.number});
  if(head.owner.toLowerCase()!==config.owner.toLowerCase())throw Error('WRONG_SIGNER');
  if(bundle.verification==='current_verified' && (head.digest!==cp.controlDigest || head.sequence.toString()!==cp.sequence))throw Error('STALE_CONTEXT');
  const logs=await registry.queryFilter(registry.filters.Advanced(config.projectId,config.owner),0,block.number);
  const accepted=logs.some(log=>'args' in log && log.args.sequence.toString()===cp.sequence && log.args.previousDigest===cp.previousDigest && log.args.controlDigest===cp.controlDigest);
  if(!accepted || (await provider.getBlock(block.number))?.hash!==block.hash)throw Error('UNVERIFIED');
  return bundle;
}

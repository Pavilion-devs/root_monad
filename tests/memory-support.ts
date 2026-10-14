import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomBytes,Wallet } from 'ethers';
import { control,signed,owner,app,bytes,baselineDomain,OWNER_KEY,APP_KEY } from './support.js';
import { hash, type ClientConfig } from '../src/client-wire.js';
export const SECOND_KEY='0x'+'33'.repeat(32);
export async function setup(){
 const snapshot={formatVersion:'0',projectId:control().projectId,previousDigest:bytes('00'),records:[],sources:[],currentIds:[],resolutions:[]};
 const second=new Wallet(SECOND_KEY);
 const c={...control(),snapshotDigest:hash('snapshot',snapshot),grants:[app,second].map(w=>({application:w.address.toLowerCase(),serviceId:control().serviceId,rights:['propose','read_current','read_history'],expiresAt:'4102444800'})).sort((a,b)=>a.application.localeCompare(b.application))};
 const genesis={...await signed(c),snapshot};
 const config={projectId:c.projectId,owner:owner.address.toLowerCase(),domain:baselineDomain};
 const client:ClientConfig={...config,serviceId:c.serviceId};
 const directory=mkdtempSync(join(tmpdir(),'portable-memory-'));
 const startup={db:join(directory,'memory.sqlite'),key:Buffer.from(randomBytes(32)).toString('hex'),config,genesis};
 return {directory,startup,client,demo:{...client,ownerKey:OWNER_KEY,planningKey:APP_KEY,codingKey:SECOND_KEY}};
}
export async function startMemory(startup:any, crash?:string, script='python/server.py'){
 const child=spawn('.venv/bin/python',crash?['tests/registry-crash-server.py',crash]:[script],{stdio:['pipe','pipe','pipe']});
 let error='';child.stderr.on('data',chunk=>{error+=chunk.toString();});
 const ready=new Promise<string>((resolve,reject)=>{
  const lines=createInterface({input:child.stdout});
  const timer=setTimeout(()=>{child.kill();reject(Error('SERVER_START_TIMEOUT'));},10000);
  lines.once('line',line=>{clearTimeout(timer);lines.close();try{resolve(JSON.parse(line).url);}catch{reject(Error('INVALID_STARTUP'));}});
  child.once('exit',code=>{clearTimeout(timer);reject(Error(`SERVER_EXIT_${code}: ${error}`));});
  child.once('error',reject);
 });
 child.stdin.end(JSON.stringify(startup)+'\n');
 const url=await ready;
 const stop=async()=>{if(child.exitCode===null && child.signalCode===null)await new Promise<void>(resolve=>{child.once('exit',()=>resolve());child.kill('SIGTERM');});};
 return {url,stop};
}

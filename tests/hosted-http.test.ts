import test from 'node:test';
import assert from 'node:assert/strict';
import {rmSync} from 'node:fs';
import {request} from 'node:http';
import {setup,startMemory} from './memory-support.js';

function fetch(url:string,options:{method?:string;headers?:Record<string,string>;body?:string}={}) {
 return new Promise<{status:number;json:()=>any}>((resolve,reject)=>{
  const req=request(url,{method:options.method??'GET',headers:{...options.headers,...(options.body?{'Content-Length':String(Buffer.byteLength(options.body))}:{})}},response=>{
   let body='';response.on('data',chunk=>body+=chunk);response.on('end',()=>resolve({status:response.statusCode!,json:()=>JSON.parse(body)}));
  });req.on('error',reject);req.end(options.body);
 });
}

test('hosted mode pins Host and Origin and never enables unsigned memory access',async()=>{
 const s=await setup();const server=await startMemory({...s.startup,bindHost:'0.0.0.0',publicOrigin:'https://memory.example'});
 try{
  assert.equal((await fetch(server.url+'/healthz',{headers:{Host:'memory.example'}})).status,200);
  assert.equal((await fetch(server.url+'/head',{headers:{Host:'memory.example',Origin:'https://memory.example'}})).status,200);
  assert.equal((await fetch(server.url+'/head',{headers:{Host:'memory.example',Origin:'https://attacker.example'}})).status,403);
  assert.equal((await fetch(server.url+'/head',{headers:{Host:'attacker.example','X-Forwarded-Host':'memory.example'}})).status,403);
  assert.equal((await fetch(server.url+'/demo-config',{headers:{Host:'memory.example'}})).status,404);
  const unsigned=await fetch(server.url+`/v0/projects/${s.client.projectId}/context`,{method:'POST',headers:{Host:'memory.example','Content-Type':'application/json'},body:'{}'});
  assert.equal(unsigned.status,400);assert.equal((await unsigned.json()).code,'INVALID_REQUEST');
 }finally{await server.stop();rmSync(s.directory,{recursive:true,force:true});}
});

import canonicalizeModule from 'canonicalize';
import { Wallet, sha256, toUtf8Bytes, verifyTypedData, randomBytes, hexlify } from 'ethers';
const canonicalize=canonicalizeModule as unknown as (value:unknown)=>string;
export const checkpointTypes={Checkpoint:['bytes32 projectId','uint256 sequence','bytes32 previousDigest','bytes32 controlDigest','uint256 deadline'].map(field)};
export const requestTypes={Request:['bytes32 projectId','bytes32 serviceId','bytes32 checkpointDigest','bytes32 requestDigest','bytes32 nonce','uint256 deadline'].map(field)};
function field(s:string){const [type,name]=s.split(' '); return {type,name};}
export const hash=(kind:string,body:unknown)=>sha256(toUtf8Bytes(`portable-memory/v0/${kind}\0`+canonicalize(body)));
export const id=()=>hexlify(randomBytes(32));
export type ClientConfig={projectId:string;owner:string;domain:any;serviceId:string};
export async function envelope(config:ClientConfig,key:string,head:string,op:string,payload:unknown){
  const body={formatVersion:'0',projectId:config.projectId,method:'POST',path:`/v0/projects/${config.projectId}/${op}`,operation:op,payload};
  const auth={projectId:config.projectId,serviceId:config.serviceId,checkpointDigest:head,requestDigest:hash('request',body),nonce:id(),deadline:String(Math.floor(Date.now()/1000)+120)};
  return {body,auth,signature:await new Wallet(key).signTypedData(config.domain,requestTypes,auth)};
}
export async function call(url:string,config:ClientConfig,key:string,op:string,payload:unknown){
  const response=await fetch(url+'/head'); if(!response.ok)throw Error('AUTHORITY_UNAVAILABLE');
  const head=await response.json(); const wire=await envelope(config,key,head.checkpointDigest,op,payload);
  return send(url,wire);
}
export async function send(url:string,wire:any){
  const response=await fetch(url+wire.body.path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(wire)});
  const result=await response.json(); if(!response.ok)throw Error(result.code??'REQUEST_FAILED');return result;
}
export function verifyContents(config:ClientConfig,bundle:any){
  const c=bundle.control,cp=bundle.checkpoint,s=bundle.snapshot;
  if(c.projectId!==config.projectId || cp.projectId!==config.projectId || s.projectId!==config.projectId ||
     cp.controlDigest!==hash('control',c) || c.snapshotDigest!==hash('snapshot',s) || cp.sequence!==c.sequence || cp.previousDigest!==c.previousDigest)
    throw Error('CONTENT_MISMATCH');
  const refs=new Map<string,any>();
  for(const r of s.records){if(refs.has(r.id))throw Error('INVALID_MANIFEST');refs.set(r.id,r);}
  const current=s.records.filter((r:any)=>r.disposition==='current').map((r:any)=>r.id).sort();
  if(JSON.stringify(current)!==JSON.stringify(s.currentIds))throw Error('INVALID_MANIFEST');
  const expected=bundle.verification==='historical_verified'? s.records.map((r:any)=>r.id).sort():current;
  if(JSON.stringify(bundle.records.map((r:any)=>r.id).sort())!==JSON.stringify(expected))throw Error('INCOMPLETE_RECORDS');
  const sourceIds=new Set<string>();
  for(const r of bundle.records){
    if(r.projectId!==config.projectId || hash('record',r)!==refs.get(r.id)?.digest)throw Error('CONTENT_MISMATCH');
    r.sourceIds.forEach((sid:string)=>sourceIds.add(sid));
  }
  const sourceRefs=new Map(s.sources.map((r:any)=>[r.id,r.digest]));
  if(sourceRefs.size!==s.sources.length)throw Error('INVALID_MANIFEST');
  if(JSON.stringify([...sourceIds].sort())!==JSON.stringify(bundle.sources.map((s:any)=>s.id).sort()))throw Error('INCOMPLETE_SOURCES');
  for(const source of bundle.sources){if(source.projectId!==config.projectId || hash('source',source)!==sourceRefs.get(source.id))throw Error('CONTENT_MISMATCH');}
}
export function verifyContext(config:ClientConfig,bundle:any){
  if(!config.domain.salt || config.domain.chainId!==undefined || bundle.authorityMode!=='signed_log' || !['current_verified','historical_verified'].includes(bundle.verification))throw Error('UNVERIFIED');
  verifyContents(config,bundle);
  if(verifyTypedData(config.domain,checkpointTypes,bundle.checkpoint,bundle.signature).toLowerCase()!==config.owner.toLowerCase())throw Error('WRONG_SIGNER');
  return bundle;
}
export function proposal(config:ClientConfig,key:string,base:string,content:string,replaces:string|null=null){
  const sourceId=id(), recordId=id();
  return {formatVersion:'0',projectId:config.projectId,id:id(),author:new Wallet(key).address.toLowerCase(),baseCheckpoint:base,
    sources:[{formatVersion:'0',projectId:config.projectId,id:sourceId,kind:'application_observation',speaker:'Demo assistant',excerpt:'Suggested in this local demonstration.',locator:null,occurredAt:null}],
    records:[{formatVersion:'0',projectId:config.projectId,id:recordId,kind:'decision',content,author:new Wallet(key).address.toLowerCase(),sourceIds:[sourceId],replaces}],retractIds:[]};
}

/** Bind owner review to the exact proposal shown, including unchanged permissions. */
export function verifyReview(config:ClientConfig,review:any,before:any,p:any,rejected:boolean){
  verifyContents(config,{...review,verification:'historical_verified'});
  const expected=structuredClone(before.snapshot);
  if(p.baseCheckpoint!==before.checkpoint.controlDigest&&!rejected)throw Error('BASE_CONFLICT');
  if(!rejected){
    const changed=new Map<string,string>();
    p.records.forEach((r:any)=>{if(r.replaces)changed.set(r.replaces,'superseded');});
    p.retractIds.forEach((rid:string)=>changed.set(rid,'retracted'));
    expected.records.forEach((r:any)=>{if(changed.has(r.id))r.disposition=changed.get(r.id);});
    expected.records.push(...p.records.map((r:any)=>({id:r.id,digest:hash('record',r),disposition:'current'})));
    expected.records.sort((a:any,b:any)=>a.id.localeCompare(b.id));
    const sources=new Map<string,any>(expected.sources.map((s:any)=>[s.id,s]));
    p.sources.forEach((s:any)=>sources.set(s.id,{id:s.id,digest:hash('source',s)}));
    expected.sources=[...sources.values()].sort((a,b)=>a.id.localeCompare(b.id));
    expected.currentIds=expected.records.filter((r:any)=>r.disposition==='current').map((r:any)=>r.id).sort();
  }
  expected.previousDigest=before.control.snapshotDigest;
  expected.resolutions.push({proposalId:p.id,proposalDigest:hash('proposal',p),state:rejected?'rejected':'accepted',reason:'Owner reviewed this proposal.'});
  expected.resolutions.sort((a:any,b:any)=>a.proposalId.localeCompare(b.proposalId));
  if(canonicalize(expected)!==canonicalize(review.snapshot))throw Error('UNEXPECTED_REVIEW_CHANGE');
  const c=review.control;
  const expectedControl={...before.control,sequence:String(BigInt(before.control.sequence)+1n),previousDigest:before.checkpoint.controlDigest,
    snapshotDigest:hash('snapshot',expected),salt:c.salt};
  if(canonicalize(c)!==canonicalize(expectedControl))throw Error('UNEXPECTED_REVIEW_CHANGE');
  if(canonicalize(review.accept)!==canonicalize(rejected?[]:[p.id])||canonicalize(review.reject)!==canonicalize(rejected?[p.id]:[]))throw Error('UNEXPECTED_REVIEW_CHANGE');
}

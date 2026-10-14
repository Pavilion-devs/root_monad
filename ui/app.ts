import { Wallet } from 'ethers';
import {call,proposal,verifyContext,verifyContents,verifyReview,checkpointTypes} from '../src/client-wire.js';
const el=(id:string)=>document.getElementById(id)!;
const select=(id:string)=>(el(id) as HTMLSelectElement).value;
const config=await (await fetch('/demo-config')).json();
let context:any, review:any, reviewBefore:any, reviewProposal:any, reviewRejected=false;
const key=(role:string)=>role==='coding'?config.codingKey:config.planningKey;
function status(message:string,error=false){el('status').textContent=message;el('status').classList.toggle('error',error);}
function node(tag:string,text:string,className=''){const n=document.createElement(tag);n.textContent=text;n.className=className;return n;}
async function action(fn:()=>Promise<void>){
 const buttons=Array.from(document.querySelectorAll('button')).map(b=>({b,disabled:b.disabled}));buttons.forEach(({b})=>b.disabled=true);
 try{await fn();}catch(e){status(e instanceof Error?friendly(e.message):'Something went wrong.',true);}
 finally{buttons.forEach(({b,disabled})=>b.disabled=disabled);}
}
function friendly(code:string){return ({BASE_CONFLICT:'The project changed while this suggestion was open. Refresh and propose it again against the current decision.',SCOPE_DENIED:'This assistant does not have permission for that action.',EXPIRED:'This review expired. Open it again before approving.'} as any)[code]??`Could not complete this action: ${code}`;}
function render(){
 el('records').replaceChildren();
 if(!context.records.length)el('records').append(node('div','No decisions yet. Send a suggestion, then review it as the owner.','empty'));
 for(const r of context.records){
  const card=node('article','','card');card.append(node('span',r.kind==='decision'?'Approved decision':r.kind==='observation'?'Recorded observation':'Open question','tag'),node('p',r.content));
  for(const sid of r.sourceIds){const s=context.sources.find((x:any)=>x.id===sid);card.append(node('div',`Source · ${s.speaker}: ${s.excerpt}`,'source'));}
  el('records').append(card);
 }
 el('version').textContent=`Version ${context.checkpoint.sequence} · Owner signature verified · ${select('reader')==='coding'?'Coding':'Planning'} assistant`;
}
async function refresh(){
 context=verifyContext(config,await call('',config,key(select('reader')),'context',{}));render();
 const inbox=await call('',config,config.ownerKey,'inbox',{});
 const pending=inbox.proposals.filter((p:any)=>p.status==='pending');
 el('count').textContent=String(pending.length);el('inbox').replaceChildren();
 if(!pending.length)el('inbox').append(node('p','You’re all caught up.','muted'));
 for(const item of pending){
  const p=item.proposal,card=node('article','','proposal');
  card.append(node('span',p.author===new Wallet(config.codingKey).address.toLowerCase()?'Coding assistant · Suggestion':'Planning assistant · Suggestion','tag'));
  card.append(node('p',p.records.map((r:any)=>r.content).join('\n')));
  if(item.stale)card.append(node('div','Based on an earlier version. Propose it again to approve.','stale'));
  const actions=node('div','','actions');
  const approve=node('button','Review change','primary') as HTMLButtonElement;
  approve.disabled=item.stale;approve.onclick=()=>action(()=>prepare(item,false));
  const reject=node('button','Reject','quiet');reject.onclick=()=>action(()=>prepare(item,true));
  actions.append(approve,reject);card.append(actions);el('inbox').append(card);
 }
 const history=verifyContext(config,await call('',config,key(select('reader')),'history',{checkpointDigest:context.checkpoint.controlDigest}));
 el('history').replaceChildren();
 for(const r of history.records){const ref=history.snapshot.records.find((x:any)=>x.id===r.id);if(ref.disposition==='current')continue;el('history').append(node('div',`${ref.disposition==='superseded'?'Replaced':'Retracted'} · ${r.content}`,'history-item'));}
 if(!el('history').childElementCount)el('history').append(node('p','No earlier decisions yet.','footnote'));
}
async function prepare(item:any,reject:boolean){
 reviewBefore=structuredClone(context);reviewProposal=structuredClone(item.proposal);reviewRejected=reject;
 review=await call('',config,config.ownerKey,'prepare',{accept:reject?[]:[item.proposal.id],reject:reject?[item.proposal.id]:[],grants:null});
 verifyReview(config,review,reviewBefore,reviewProposal,reviewRejected);
 const old=item.proposal.records.map((r:any)=>context.records.find((x:any)=>x.id===r.replaces)?.content).filter(Boolean);
 el('review-title').textContent=reject?'Reject this suggestion?':'Approve this decision?';
 el('review-content').textContent=(old.length?'Current\n'+old.join('\n')+'\n\n':'')+(reject?'Reject\n':'Proposed\n')+item.proposal.records.map((r:any)=>r.content).join('\n');
 el('approve').textContent=reject?'Confirm rejection':'Approve decision';
 (el('review') as HTMLDialogElement).showModal();
}
el('refresh').onclick=()=>action(async()=>{await refresh();status('Both assistants can retrieve the accepted project context.');});
el('reader').onchange=()=>action(async()=>{await refresh();status('Context retrieved and owner signature verified.');});
el('mode').onchange=()=>{if(select('mode')==='correct')(el('suggestion') as HTMLTextAreaElement).value='Retain project notes for 14 days.';};
el('propose').onclick=()=>action(async()=>{
 const content=(el('suggestion') as HTMLTextAreaElement).value.trim();if(!content)throw Error('Write a suggestion first.');
 const ctx=verifyContext(config,await call('',config,key(select('author')),'context',{}));
 const replaces=select('mode')==='correct'?ctx.records[0]?.id:null;
 if(select('mode')==='correct'&&!replaces)throw Error('Approve a decision before correcting it.');
 const p=proposal(config,key(select('author')),ctx.checkpoint.controlDigest,content,replaces??null);
 await call('',config,key(select('author')),'proposals',p);await refresh();status('Suggestion saved. Shared decisions remain unchanged until you approve it.');
});
el('approve').onclick=()=>action(async()=>{
 const pending=review;
 verifyReview(config,pending,reviewBefore,reviewProposal,reviewRejected);
 const signature=await new Wallet(config.ownerKey).signTypedData(config.domain,checkpointTypes,pending.checkpoint);
 await call('',config,config.ownerKey,'commit',{checkpoint:pending.checkpoint,signature});
 (el('review') as HTMLDialogElement).close();await refresh();status('Review saved. Both assistants can now retrieve this version.');
});
for(const id of ['close-review','cancel-review'])el(id).onclick=()=>{(el('review') as HTMLDialogElement).close();review=null;};
await action(async()=>{await refresh();status('Ready. Start with a suggestion from either assistant.');});

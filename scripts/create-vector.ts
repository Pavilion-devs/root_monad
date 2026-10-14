import { writeFileSync } from 'node:fs';
import { OWNER_KEY, APP_KEY, owner, app, control, signed, baselineDomain, bytes, NOW } from '../tests/support.js';
import { digest,TYPES,type RequestBody } from '../src/protocol.js';
const genesis=await signed(control());
const requestBody:RequestBody={formatVersion:'0',projectId:genesis.control.projectId,method:'POST',
  path:`/v0/projects/${genesis.control.projectId}/context`,operation:'context',payload:{query:'What did we decide? Café 😀'}};
const requestAuth={projectId:genesis.control.projectId,serviceId:genesis.control.serviceId,
  checkpointDigest:genesis.checkpoint.controlDigest,requestDigest:digest('request',requestBody),nonce:bytes('99'),deadline:String(NOW+60n)};
const vector={warning:'Public test-only keys. Never fund these identities.',owner:owner.address.toLowerCase(),app:app.address.toLowerCase(),
  testOwnerKey:OWNER_KEY,testAppKey:APP_KEY,domain:baselineDomain,control:genesis.control,checkpoint:genesis.checkpoint,
  checkpointSignature:genesis.signature,requestBody,requestAuth,requestSignature:await app.signTypedData(baselineDomain,{Request:TYPES.Request},requestAuth)};
writeFileSync('fixtures/authority-vector.json',JSON.stringify(vector,null,2)+'\n');

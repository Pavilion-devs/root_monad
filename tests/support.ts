import { Wallet } from 'ethers';
import { ZERO, digest, projectId, TYPES, type Control, type Checkpoint } from '../src/protocol.js';
// Public throwaway keys used only by local fixtures. Never fund these addresses.
export const OWNER_KEY = '0x' + '11'.repeat(32);
export const APP_KEY = '0x' + '22'.repeat(32);
export const owner = new Wallet(OWNER_KEY);
export const app = new Wallet(APP_KEY);
export const bytes = (byte:string) => '0x'+byte.repeat(32);
export const nonce = bytes('33');
export const project = projectId(owner.address,nonce);
export const baselineDomain = {name:'PortableMemory',version:'0',salt:bytes('44')};
export const NOW = 2_000_000_000n;
export function control(sequence='0', previousDigest=ZERO, salt='55'):Control {
  return {formatVersion:'0',projectId:project,sequence,previousDigest,creationNonce:nonce,
    snapshotDigest:bytes('66'), serviceId:bytes('77'),
    grants:[{application:app.address.toLowerCase(),serviceId:bytes('77'),rights:['propose','read_current'],expiresAt:'4102444800'}],
    storage:{providerId:bytes('88'),locator:'fixture://provider-one/π/😀'},salt:bytes(salt)};
}
export async function signed(body:Control,domain:any=baselineDomain,deadline='4102444800',wallet=owner) {
  const checkpoint:Checkpoint = {projectId:body.projectId,sequence:body.sequence,previousDigest:body.previousDigest,
    controlDigest:digest('control',body),deadline};
  const signature=await wallet.signTypedData(domain,{Checkpoint:TYPES.Checkpoint},checkpoint);
  return {checkpoint,control:body,signature};
}

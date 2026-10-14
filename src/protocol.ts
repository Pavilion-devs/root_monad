import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { Ajv } from 'ajv';
const canonicalize: (value: unknown) => string | undefined = createRequire(import.meta.url)('canonicalize');
import { visit } from 'jsonc-parser';
import { AbiCoder, keccak256, verifyTypedData, type TypedDataDomain } from 'ethers';

export const ZERO = '0x' + '00'.repeat(32);
export const MAX_UINT = (1n << 256n) - 1n;
export type Checkpoint = {projectId: string; sequence: string; previousDigest: string; controlDigest: string; deadline: string};
export type Grant = {application: string; serviceId: string; rights: string[]; expiresAt: string};
export type Control = {formatVersion: '0'; projectId: string; sequence: string; previousDigest: string;
  creationNonce: string; snapshotDigest: string; grants: Grant[]; serviceId: string;
  storage: {providerId: string; locator: string}; salt: string};
export type RequestBody = {formatVersion: '0'; projectId: string; method: 'POST'; path: string;
  operation: 'context' | 'history' | 'proposals' | 'inbox' | 'prepare' | 'commit'; payload: Record<string, unknown>};
export type RequestAuth = {projectId: string; serviceId: string; checkpointDigest: string;
  requestDigest: string; nonce: string; deadline: string};
export const TYPES = {
  Checkpoint: ['bytes32 projectId', 'uint256 sequence', 'bytes32 previousDigest', 'bytes32 controlDigest', 'uint256 deadline'].map(field),
  Request: ['bytes32 projectId','bytes32 serviceId','bytes32 checkpointDigest','bytes32 requestDigest','bytes32 nonce','uint256 deadline'].map(field)
};
function field(value: string) { const [type, name] = value.split(' '); return {name, type}; }
const ajv = new Ajv({allErrors: true, strict: true});
const validators = Object.fromEntries(['control','checkpoint','request','request-auth','source','record','proposal','snapshot'].map(name =>
  [name, ajv.compile(JSON.parse(readFileSync(new URL(`../schemas/${name}.schema.json`, import.meta.url), 'utf8')))]));
export function strictParse(text: string): unknown {
  const stack: Set<string>[] = [];
  visit(text, {onObjectBegin: () => {stack.push(new Set());}, onObjectEnd: () => {stack.pop();},
    onObjectProperty: key => {const keys = stack.at(-1)!; if (keys.has(key)) throw Error('DUPLICATE_KEY'); keys.add(key);}});
  const value = JSON.parse(text); canonical(value); return value;
}
function unicode(value: unknown): void {
  if (typeof value === 'string') {
    for (const ch of value) {const n = ch.codePointAt(0)!; if (n >= 0xd800 && n <= 0xdfff) throw Error('INVALID_UNICODE');}
  } else if (typeof value === 'number') {
    if (!Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER) throw Error('UNSAFE_NUMBER');
  } else if (Array.isArray(value)) value.forEach(unicode);
  else if (value && typeof value === 'object') Object.entries(value).forEach(([k,v]) => {unicode(k); unicode(v);});
}
export function canonical(body: unknown): string {unicode(body); const s = canonicalize(body); if (!s) throw Error('INVALID_JSON'); return s;}
export function digest(type: 'control' | 'request' | 'source' | 'record' | 'proposal' | 'snapshot', body: unknown): string {
  validate(type, body);
  return '0x' + createHash('sha256').update(`portable-memory/v0/${type}\0`).update(canonical(body)).digest('hex');
}
export function validate(type: string, body: any): void {
  canonical(body);
  const valid = Boolean(validators[type]?.(body));
  if (!valid) throw Error('INVALID_SCHEMA: ' + JSON.stringify(validators[type]?.errors));
  for (const key of ['sequence','deadline']) if (body[key] !== undefined && BigInt(body[key]) > MAX_UINT) throw Error('UINT_OVERFLOW');
  if (type === 'control') {
    const addresses = body.grants.map((g: Grant) => g.application);
    if (canonical(addresses) !== canonical([...new Set(addresses)].sort())) throw Error('UNSORTED_GRANTS');
    for (const g of body.grants as Grant[]) {
      if (g.serviceId !== body.serviceId || BigInt(g.expiresAt) > MAX_UINT) throw Error('INVALID_GRANT');
      if (canonical(g.rights) !== canonical([...g.rights].sort())) throw Error('UNSORTED_RIGHTS');
    }
  }
  if (type === 'request' && body.path !== `/v0/projects/${body.projectId}/${body.operation}`) throw Error('WRONG_PATH');
}
export function projectId(owner: string, nonce: string): string {
  return keccak256(AbiCoder.defaultAbiCoder().encode(['address','bytes32'],[owner,nonce]));
}
export function checkSignature(signature: string): void {
  const order = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
  if (!/^0x[0-9a-fA-F]{130}$/.test(signature)) throw Error('INVALID_SIGNATURE');
  const r = BigInt('0x' + signature.slice(2,66));
  const s = BigInt('0x' + signature.slice(66,130));
  const v = parseInt(signature.slice(130),16);
  if (r === 0n || r >= order || s === 0n || s > order/2n || ![27,28].includes(v)) throw Error('INVALID_SIGNATURE');
}
export function verifyOwner(domain: TypedDataDomain, cp: Checkpoint, control: Control, signature: string, owner: string): void {
  checkSignature(signature);
  validate('checkpoint', cp); validate('control', control);
  if (cp.projectId !== control.projectId || cp.sequence !== control.sequence || cp.previousDigest !== control.previousDigest ||
      cp.controlDigest !== digest('control',control) || cp.controlDigest === ZERO || cp.controlDigest === cp.previousDigest ||
      projectId(owner,control.creationNonce) !== cp.projectId) throw Error('CONTENT_MISMATCH');
  if (verifyTypedData(domain,{Checkpoint:TYPES.Checkpoint},cp,signature).toLowerCase() !== owner.toLowerCase()) throw Error('WRONG_SIGNER');
}

/** One replica's signed log. A second replica can accept a different valid successor. */
export class SignedLog {
  private entries: {checkpoint: Checkpoint; control: Control; signature: string}[] = [];
  constructor(readonly owner: string, readonly domain: TypedDataDomain) {
    if (!domain.salt || domain.chainId !== undefined || domain.verifyingContract !== undefined) throw Error('BASELINE_DOMAIN_REQUIRED');
  }
  get head() {return structuredClone(this.entries.at(-1));}
  append(cp: Checkpoint, control: Control, signature: string, now: bigint): void {
    verifyOwner(this.domain,cp,control,signature,this.owner);
    if (BigInt(cp.deadline) < now) throw Error('EXPIRED');
    const old = this.head;
    if (cp.previousDigest !== (old?.checkpoint.controlDigest ?? ZERO) ||
        BigInt(cp.sequence) !== (old ? BigInt(old.checkpoint.sequence) + 1n : 0n)) throw Error('BASE_CONFLICT');
    this.entries.push(structuredClone({checkpoint:cp,control,signature}));
  }
  export() {return structuredClone(this.entries);}
  static fromHistory(owner: string, domain: TypedDataDomain, entries: ReturnType<SignedLog['export']>) {
    const log = new SignedLog(owner,domain);
    for (const entry of entries) {
      // Imported history verifies authorship/order, not when it was first received or whether it is latest.
      verifyOwner(domain,entry.checkpoint,entry.control,entry.signature,owner);
      const old=log.head;
      if (entry.checkpoint.previousDigest !== (old?.checkpoint.controlDigest ?? ZERO) ||
          BigInt(entry.checkpoint.sequence) !== (old ? BigInt(old.checkpoint.sequence)+1n : 0n)) throw Error('BASE_CONFLICT');
      log.entries.push(structuredClone(entry));
    }
    return log;
  }
}

/** Offchain permission boundary; registry alone never enforces encrypted grants. */
export class RequestGate {
  private nonces = new Map<string, {fingerprint:string; result:unknown}>();
  constructor(readonly domain: TypedDataDomain) {}
  execute(control: Control, auth: RequestAuth, body: RequestBody, signature: string, now: bigint, action: () => unknown): unknown {
    validate('control',control); validate('request-auth',auth); validate('request',body);
    if (auth.projectId !== control.projectId || body.projectId !== control.projectId || auth.serviceId !== control.serviceId) throw Error('WRONG_AUDIENCE');
    if (auth.checkpointDigest !== digest('control',control)) throw Error('BASE_CONFLICT');
    if (BigInt(auth.deadline) < now || BigInt(auth.deadline) > now + 300n) throw Error('EXPIRED_REQUEST');
    if (auth.requestDigest !== digest('request',body)) throw Error('CONTENT_MISMATCH');
    checkSignature(signature);
    const signer = verifyTypedData(this.domain,{Request:TYPES.Request},auth,signature).toLowerCase();
    const right = {context:'read_current',history:'read_history',proposals:'propose',inbox:'read_current',prepare:'owner',commit:'owner'}[body.operation];
    const grant = control.grants.find(g => g.application === signer && g.serviceId === auth.serviceId);
    if (!grant || BigInt(grant.expiresAt) < now || !grant.rights.includes(right)) throw Error('SCOPE_DENIED');
    const key = `${control.projectId}:${signer}:${auth.nonce}`;
    const fingerprint = canonical(auth);
    const seen = this.nonces.get(key);
    if (seen) {if (seen.fingerprint !== fingerprint) throw Error('REPLAY_MISMATCH'); return structuredClone(seen.result);}
    const result = action();
    this.nonces.set(key,{fingerprint,result:structuredClone(result)});
    return result;
  }
}

import canonicalize from 'canonicalize';
import { AbiCoder, BrowserProvider, Interface, hexlify, keccak256, randomBytes, sha256, toUtf8Bytes, verifyTypedData } from 'ethers';

export const ZERO = '0x' + '00'.repeat(32);
export const types = {Checkpoint: ['bytes32 projectId', 'uint256 sequence', 'bytes32 previousDigest', 'bytes32 controlDigest', 'uint256 deadline'].map(s => {
  const [type, name] = s.split(' '); return {type, name};
})};
const abi = new Interface([
  'function create(address owner, bytes32 creationNonce, (bytes32 projectId,uint256 sequence,bytes32 previousDigest,bytes32 controlDigest,uint256 deadline) checkpoint, bytes signature)',
  'function heads(bytes32) view returns (address owner,uint256 sequence,bytes32 digest)',
  'function acceptedAt(bytes32,uint256) view returns (uint256)',
  'event Advanced(bytes32 indexed projectId,address indexed owner,uint256 sequence,bytes32 previousDigest,bytes32 controlDigest)',
]);
export const hash = (kind, body) => sha256(toUtf8Bytes(`portable-memory/v0/${kind}\0` + canonicalize(body)));
export const randomId = () => hexlify(randomBytes(32));
const same = (a, b) => canonicalize(a) === canonicalize(b);
function require(ok, message) { if (!ok) throw Error(message); }

export function buildGenesis(settings, owner, nonce = randomId(), salt = randomId(), now = Math.floor(Date.now()/1000)) {
  const projectId = keccak256(AbiCoder.defaultAbiCoder().encode(['address', 'bytes32'], [owner, nonce]));
  const snapshot = {formatVersion: '0', projectId, previousDigest: ZERO, records: [], sources: [], currentIds: [], resolutions: []};
  const control = {formatVersion: '0', projectId, sequence: '0', previousDigest: ZERO, creationNonce: nonce,
    snapshotDigest: hash('snapshot', snapshot), grants: [], serviceId: settings.serviceId,
    storage: {providerId: settings.providerId, locator: `project:${projectId}`}, salt};
  const checkpoint = {projectId, sequence: '0', previousDigest: ZERO, controlDigest: hash('control', control), deadline: String(now + 900)};
  return {snapshot, control, checkpoint};
}

export function verifyGenesis(settings, owner, genesis) {
  require(/^0x[0-9a-f]{40}$/.test(owner), 'WRONG_WALLET');
  const expected = buildGenesis(settings, owner, genesis.control.creationNonce, genesis.control.salt, Number(genesis.checkpoint.deadline) - 900);
  require(same(expected.snapshot, genesis.snapshot) && same(expected.control, genesis.control) && same(expected.checkpoint, genesis.checkpoint), 'SETUP_MISMATCH');
  require(verifyTypedData(settings.domain, types, genesis.checkpoint, genesis.signature).toLowerCase() === owner, 'WRONG_SIGNER');
}

export function creationTransaction(settings, owner, genesis) {
  verifyGenesis(settings, owner, genesis);
  return {from: owner, to: settings.domain.verifyingContract, chainId: '0x279f', value: '0x0',
    data: abi.encodeFunctionData('create', [owner, genesis.control.creationNonce, genesis.checkpoint, genesis.signature])};
}

export function verifyStatus(settings, owner, result, expectedGenesis) {
  require(result.owner === owner && same(result.domain, settings.domain) && result.serviceId === settings.serviceId, 'SETUP_MISMATCH');
  verifyGenesis(settings, owner, result.genesis);
  require(result.projectId === result.genesis.checkpoint.projectId, 'SETUP_MISMATCH');
  if (expectedGenesis) require(same(result.genesis, expectedGenesis), 'SETUP_MISMATCH');
  const {from, ...expected} = creationTransaction(settings, owner, result.genesis);
  require(same(result.transaction, {...expected, kind: 'external_wallet'}), 'SETUP_MISMATCH');
  require(['pending', 'ready'].includes(result.status) && result.verified === (result.status === 'ready'), 'SETUP_MISMATCH');
  return result;
}

export async function walletAccount(provider, owner) {
  require(await provider.request({method: 'eth_chainId'}) === '0x279f', 'WRONG_CHAIN');
  const accounts = await provider.request({method: 'eth_accounts'});
  require(accounts[0]?.toLowerCase() === owner, 'WALLET_CHANGED');
}

export async function checkRegistry(provider, settings) {
  require(settings.domain.chainId === 10143 && settings.domain.name === 'PortableMemory' && settings.domain.version === '0', 'WRONG_CHAIN');
  const code = await provider.request({method: 'eth_getCode', params: [settings.domain.verifyingContract, 'latest']});
  require(keccak256(code) === settings.runtimeCodeHash, 'REGISTRY_MISMATCH');
}

export async function signGenesis(provider, settings, owner, genesis) {
  await walletAccount(provider, owner); await checkRegistry(provider, settings);
  require(Number(genesis.checkpoint.deadline) > Date.now()/1000, 'SETUP_EXPIRED');
  const signer = await new BrowserProvider(provider).getSigner(owner);
  const signature = await signer.signTypedData(settings.domain, types, genesis.checkpoint);
  await walletAccount(provider, owner);
  const signed = {...genesis, signature}; verifyGenesis(settings, owner, signed); return signed;
}

export async function verifyFinalized(provider, settings, owner, result) {
  await walletAccount(provider, owner); await checkRegistry(provider, settings);
  const rpc = (method, params) => provider.request({method, params});
  const block = await rpc('eth_getBlockByNumber', ['finalized', false]);
  const now = Math.floor(Date.now()/1000), timestamp = Number(BigInt(block?.timestamp || '0x0'));
  require(block?.hash && block?.number && now - timestamp <= 120 && timestamp - now <= 30, 'CHAIN_UNAVAILABLE');
  const call = async (method, args) => abi.decodeFunctionResult(method, await rpc('eth_call', [{to: settings.domain.verifyingContract, data: abi.encodeFunctionData(method, args)}, block.number]));
  const [chainOwner, sequence, digest] = await call('heads', [result.projectId]);
  require(chainOwner.toLowerCase() === owner && String(sequence) === result.sequence && digest === result.checkpointDigest, 'CHAIN_MISMATCH');
  // Verify the original signed genesis was actually accepted, including its receipt.
  const [acceptedAt] = await call('acceptedAt', [result.projectId, 0]);
  require(acceptedAt > 0n && acceptedAt <= BigInt(block.number), 'CHAIN_MISMATCH');
  const number = '0x' + acceptedAt.toString(16);
  const topics = abi.encodeFilterTopics('Advanced', [result.projectId, owner]);
  const logs = await rpc('eth_getLogs', [{address: settings.domain.verifyingContract, fromBlock: number, toBlock: number, topics}]);
  const matches = logs.filter(log => {
    const event = abi.parseLog(log);
    return !log.removed && log.address.toLowerCase() === settings.domain.verifyingContract.toLowerCase() && event?.args.sequence === 0n &&
      event.args.previousDigest === ZERO && event.args.controlDigest === result.genesis.checkpoint.controlDigest;
  });
  require(matches.length === 1, 'CHAIN_MISMATCH');
  const event = matches[0], receipt = await rpc('eth_getTransactionReceipt', [event.transactionHash]);
  const inclusion = await rpc('eth_getBlockByNumber', [number, false]);
  require(receipt?.status === '0x1' && receipt.blockHash === event.blockHash && inclusion?.hash === event.blockHash &&
    receipt.blockNumber === number && receipt.transactionHash === event.transactionHash &&
    receipt.to?.toLowerCase() === settings.domain.verifyingContract.toLowerCase() &&
    receipt.logs.some(log => log.address.toLowerCase() === event.address.toLowerCase() && log.data === event.data && same(log.topics, event.topics)), 'CHAIN_MISMATCH');
  const stable = await rpc('eth_getBlockByNumber', [block.number, false]);
  const stableReceipt = await rpc('eth_getTransactionReceipt', [event.transactionHash]);
  require(stable?.hash === block.hash && same(stableReceipt, receipt), 'CHAIN_UNAVAILABLE');
  await walletAccount(provider, owner);
  return {transactionHash: event.transactionHash, sequence: result.sequence};
}

export async function walletApi(path, body) {
  const response = await fetch('/wallet/' + path, {method: body ? 'POST' : 'GET', cache: 'no-store',
    signal: AbortSignal.timeout(30000), headers: body ? {'Content-Type': 'application/json'} : {},
    ...(body ? {body: JSON.stringify(body)} : {})});
  const data = await response.json(); if (!response.ok) throw Error(data.code || 'SERVICE_UNAVAILABLE'); return data;
}

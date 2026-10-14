import React, {useEffect, useRef, useState} from 'react';
import {buildGenesis, checkRegistry, creationTransaction, signGenesis, verifyFinalized, verifyStatus, walletAccount, walletApi} from './wallet.js';
import './dashboard.css';
import './onboarding.css';

const STORE = 'portable-memory.wallet-project.v1';
const short = value => value ? `${value.slice(0, 8)}…${value.slice(-6)}` : '';
const messages = {
  NO_WALLET: 'Open this page in a browser with an Ethereum wallet extension, then refresh. The Codex browser may not have a wallet installed.',
  WRONG_CHAIN: 'Switch your wallet to Monad Testnet, then reconnect.',
  WALLET_CHANGED: 'Your wallet account or network changed. Reconnect before continuing. Your saved project is still here.',
  REGISTRY_MISMATCH: 'The registry does not match the deployment we trust. Creation has stopped.',
  SETUP_MISMATCH: 'The saved setup does not match this project. No transaction was requested.',
  WRONG_SIGNER: 'This setup was signed by a different wallet.',
  WRONG_WALLET: 'Connect the wallet that owns this project to recover it.',
  SETUP_EXPIRED: 'This unsigned setup expired. Go back and review a new setup.',
  EXPIRED: 'This setup expired before it could be saved. Review a new setup.',
  PROJECT_NOT_FOUND: 'We could not find that project on this service. Check the project ID and service address.',
  CHAIN_MISMATCH: 'The project and finalized chain state do not match. No success is being claimed.',
  CHAIN_UNAVAILABLE: 'We could not verify fresh finalized chain state. Check again shortly.',
  AUTHORITY_UNAVAILABLE: 'Monad is temporarily unavailable. Your saved setup can be checked again.',
  CAPACITY_REACHED: 'This preview has reached its project limit. Please contact the operator.',
  OWNER_PROJECT_LIMIT: 'This preview allows three projects per wallet, including pending setups. Recover an existing project below.',
};
function explain(error) {
  if (error.code === 4001 || error.code === 'ACTION_REJECTED') return 'You cancelled in your wallet. Nothing new was submitted by this page.';
  if (error.code === 4902) return 'Add Monad Testnet to your wallet first (chain ID 10143), then connect again.';
  return messages[error.message] || 'We could not complete that step. Check your wallet and connection, then try checking again.';
}
function readSaved() {
  try {
    const value = JSON.parse(localStorage.getItem(STORE));
    return value?.version === 1 && /^0x[0-9a-f]{64}$/.test(value.projectId) &&
      /^0x[0-9a-f]{40}$/.test(value.owner) && value.genesis?.checkpoint && typeof value.origin === 'string' ? value : null;
  } catch { return null; }
}

export default function Onboarding() {
  const [settings, setSettings] = useState(null), [wallets, setWallets] = useState([]), [selected, setSelected] = useState('');
  const [owner, setOwner] = useState(''), [name, setName] = useState('My project'), [draft, setDraft] = useState(null);
  const [saved, setSaved] = useState(readSaved), [result, setResult] = useState(null), [recovery, setRecovery] = useState('');
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const inFlight = useRef(false), generation = useRef(0);
  const wallet = wallets.find(item => item.id === selected)?.provider;

  async function run(message, task) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(message); setError(''); setNotice('');
    try { await task(); } catch (failure) { setError(explain(failure)); }
    finally { inFlight.current = false; setBusy(''); }
  }
  function persist(value) {
    // Save before opening a transaction prompt. Failure to save blocks submission.
    localStorage.setItem(STORE, JSON.stringify(value)); setSaved(value);
  }
  useEffect(() => {
    document.title = 'Create your project · Portable Memory';
    const announced = event => {
      const detail = event.detail;
      if (!detail?.provider?.request || !detail?.info?.uuid) return;
      setWallets(previous => previous.some(item => item.id === detail.info.uuid) ? previous : [...previous,
        {id: detail.info.uuid, name: String(detail.info.name).slice(0, 60), provider: detail.provider}]);
      setSelected(value => value || detail.info.uuid);
    };
    window.addEventListener('eip6963:announceProvider', announced);
    window.dispatchEvent(new Event('eip6963:requestProvider'));
    if (window.ethereum?.request) {
      setWallets(previous => [...previous, {id: 'injected', name: 'Browser wallet', provider: window.ethereum}]);
      setSelected(value => value || 'injected');
    }
    run('Opening project setup…', async () => setSettings(await walletApi('config')));
    return () => window.removeEventListener('eip6963:announceProvider', announced);
  }, []);
  useEffect(() => {
    const changed = () => { generation.current++; setOwner(''); setDraft(null); setResult(null); setError(messages.WALLET_CHANGED); };
    wallet?.on?.('accountsChanged', changed); wallet?.on?.('chainChanged', changed);
    return () => { wallet?.removeListener?.('accountsChanged', changed); wallet?.removeListener?.('chainChanged', changed); };
  }, [wallet]);
  function guard(version) { if (version !== generation.current) throw Error('WALLET_CHANGED'); }
  async function connect() {
    if (!wallet) throw Error('NO_WALLET');
    await wallet.request({method: 'eth_requestAccounts'});
    if (await wallet.request({method: 'eth_chainId'}) !== '0x279f') {
      await wallet.request({method: 'wallet_switchEthereumChain', params: [{chainId: '0x279f'}]});
    }
    const account = (await wallet.request({method: 'eth_accounts'}))[0]?.toLowerCase();
    if (!account) throw Error('NO_WALLET');
    await checkRegistry(wallet, settings); await walletAccount(wallet, account);
    setOwner(account); setError(''); setDraft(null); setResult(null);
  }
  async function stage() {
    const version = generation.current;
    const signed = await signGenesis(wallet, settings, owner, draft.genesis); guard(version);
    // Retain the exact signed setup even if the server saves it but its response is lost.
    const record = {version: 1, origin: location.origin, name, owner, projectId: signed.checkpoint.projectId,
      serviceId: settings.serviceId, domain: settings.domain, genesis: signed, attempted: false};
    persist(record);
    const data = verifyStatus(settings, owner, await walletApi('projects', {owner, genesis: signed}), signed);
    if (data.status === 'ready') await verifyFinalized(wallet, settings, owner, data);
    guard(version); setDraft(null); setResult(data); setNotice(data.status === 'ready' ? 'Project creation verified against finalized Monad state.' : 'Your setup is saved. Confirm the transaction below to create the project on Monad.');
  }
  async function check(record = saved) {
    const version = generation.current;
    if (!record || record.owner !== owner) throw Error('WRONG_WALLET');
    if (record.origin !== location.origin || record.serviceId !== settings.serviceId) throw Error('SETUP_MISMATCH');
    setResult(null); await walletAccount(wallet, owner);
    let data;
    try { data = await walletApi('projects/' + record.projectId); }
    catch (failure) {
      // Retrying the exact signed stage is idempotent, including a lost response.
      if (failure.message !== 'PROJECT_NOT_FOUND' || !record.genesis) throw failure;
      data = await walletApi('projects', {owner, genesis: record.genesis});
    }
    verifyStatus(settings, owner, data, record.genesis);
    if (data.status === 'ready') await verifyFinalized(wallet, settings, owner, data);
    guard(version); setResult(data);
    setNotice(data.status === 'ready' ? 'Project ownership and creation verified against finalized Monad state.' : 'Your setup is saved. Creation is not yet verified.');
  }
  async function submit() {
    const version = generation.current;
    await walletAccount(wallet, owner); await checkRegistry(wallet, settings); guard(version);
    // Re-read before sending to avoid submitting a project that already finalized.
    const status = verifyStatus(settings, owner, await walletApi('projects/' + saved.projectId), saved.genesis);
    guard(version);
    if (status.status === 'ready') return check();
    if (saved.attempted) throw Error('CHECK_PENDING');
    if (Number(saved.genesis.checkpoint.deadline) <= Date.now()/1000) throw Error('SETUP_EXPIRED');
    const transaction = creationTransaction(settings, owner, saved.genesis);
    await walletAccount(wallet, owner); guard(version);
    persist({...saved, attempted: true});
    let tx;
    try { tx = await wallet.request({method: 'eth_sendTransaction', params: [transaction]}); }
    catch (failure) {
      if (failure.code === 4001) persist({...saved, attempted: false});
      else setNotice('Submission is uncertain. Check your wallet history and check this project before trying another transaction.');
      throw failure;
    }
    persist({...saved, attempted: true, transactionHash: tx}); guard(version);
    setNotice('Transaction submitted. Check confirmation when your wallet shows it has completed.');
  }
  async function recover() {
    const project = recovery.trim().toLowerCase();
    if (!/^0x[0-9a-f]{64}$/.test(project)) throw Error('PROJECT_NOT_FOUND');
    const version = generation.current;
    await walletAccount(wallet, owner);
    const data = verifyStatus(settings, owner, await walletApi('projects/' + project)); guard(version);
    const record = {version: 1, origin: location.origin, name: 'Recovered project', owner, projectId: project,
      serviceId: settings.serviceId, domain: settings.domain, genesis: data.genesis,
      // With no local submission history, only read/check. Never guess that it is safe to resend.
      attempted: true};
    persist(record); setDraft(null); await check(record);
  }
  function download() {
    const receipt = {version: 1, service: location.origin, projectId: saved.projectId, owner: saved.owner,
      serviceId: saved.serviceId, domain: saved.domain};
    const url = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], {type: 'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = 'portable-memory-project.json'; a.click(); URL.revokeObjectURL(url);
  }
  const ready = result?.status === 'ready' && result.verified;
  return <div className="pm-shell pm-onboarding"><header className="pm-onboard-header"><a className="pm-brand" href="/start">Portable<span className="pm-brand-light">Memory</span></a><span className="pm-tag">Monad Testnet</span></header>
    <main className="pm-onboard-layout"><aside className="pm-onboard-intro"><span className="pm-eyebrow">YOUR CONTEXT. YOUR CALL.</span><h1>A home for what<br/>your assistants know.</h1><p>Create a project you own. Connect your assistants, carry context between them, and keep the final say on what gets remembered.</p>
      <ol className="pm-setup-steps"><li className={owner ? 'complete' : 'active'}><span>01</span><div><strong>Connect your wallet</strong><small>Your wallet holds project authority.</small></div></li><li className={draft || saved?.owner === owner ? 'active' : ''}><span>02</span><div><strong>Review your setup</strong><small>Start with empty memory and no app access.</small></div></li><li className={ready ? 'complete' : ''}><span>03</span><div><strong>Create on Monad</strong><small>Confirm ownership, then verify the result.</small></div></li></ol>
      <p className="pm-onboard-privacy">Memory content stays offchain. This service can read stored content; your wallet key stays in your wallet. Monad records ownership and version commitments.</p></aside>
    <section className="pm-onboard-card" aria-label="Project setup">
      {busy && <p className="pm-onboard-status" role="status">{busy}</p>}{error && <div className="pm-onboard-error" role="alert">{error}</div>}{notice && <p className="pm-onboard-status" role="status">{notice}</p>}
      {!settings ? <><h2>Opening setup</h2><p>Loading the project's network and service details.</p><button className="pm-button" disabled={!!busy} onClick={() => run('Loading…', async () => setSettings(await walletApi('config')))}>Try again</button></> : !owner ? <>
        <span className="pm-eyebrow">LET'S GET YOU SET UP</span><h2>It starts with your wallet.</h2><p>Use a wallet you control. Connecting reveals your address; it does not create a project or send a transaction.</p>
        {!!wallets.length && <label>Choose wallet<select value={selected} disabled={!!busy} onChange={e => {generation.current++; setSelected(e.target.value); setResult(null);}}>{wallets.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <button className="pm-button pm-primary" disabled={!!busy} onClick={() => run('Connecting your wallet…', connect)}>Connect wallet <span aria-hidden="true">↗</span></button>
        {!wallets.length && <p className="pm-onboard-hint">No browser wallet detected. Open this page in your wallet-enabled browser. You will need Monad Testnet and test MON for the creation transaction.</p>}
        <div className="pm-onboard-footnote">This preview supports standard Ethereum wallet accounts. Smart contract wallets and mobile wallet pairing come later.</div>
      </> : ready ? <><span className="pm-tag">Verified on Monad</span><h2>Your project is yours.</h2><p>{saved?.name || 'Your project'} has a confirmed owner and a verified creation record. {result.sequence === '0' ? 'It starts with no memory and no connected apps.' : `The current revision is ${result.sequence}.`}</p><dl><dt>Owner</dt><dd>{short(owner)}</dd><dt>Project</dt><dd className="pm-break">{result.projectId}</dd><dt>Revision</dt><dd>{result.sequence}</dd></dl><button className="pm-button pm-primary" onClick={download}>Save project receipt</button><div className="pm-onboard-next"><strong>Next: connect an assistant</strong><p>Wallet-based assistant enrollment is the next step being built. No assistant has been granted access by this setup.</p></div><button className="pm-button" disabled={!!busy} onClick={() => run('Rechecking Monad…', () => check())}>Check again</button></> : result || (saved?.owner === owner && !draft) ? <>
        <span className="pm-eyebrow">SETUP SAVED</span><h2>Make it yours on Monad.</h2><p>Your wallet will show a transaction to create this project. It uses test MON for network fees and grants no assistant access.</p><dl><dt>Owner</dt><dd>{short(owner)}</dd><dt>Project</dt><dd className="pm-break">{saved.projectId}</dd><dt>Registry</dt><dd>{short(settings.domain.verifyingContract)}</dd></dl>
        {!saved.attempted && <button className="pm-button pm-primary" disabled={!!busy || !result} onClick={() => run('Confirm creation in your wallet…', submit)}>Create on Monad</button>}
        <button className="pm-button" disabled={!!busy} onClick={() => run('Checking saved project…', () => check())}>Check confirmation</button><button className="pm-button" onClick={download}>Save project receipt</button>
        {saved.attempted && <p className="pm-onboard-hint">A transaction may already have been submitted. Check confirmation to recover it. This page will not automatically send it again.</p>}
        <details><summary>Project details</summary><code className="pm-break">{saved.transactionHash || 'No transaction hash saved yet.'}</code><p>The receipt helps you find this project again. It is not a backup of its memory content.</p></details>
      </> : draft ? <><span className="pm-eyebrow">REVIEW BEFORE SIGNING</span><h2>{name}</h2><p>You are creating an empty project under your wallet. Signing this setup authorizes only this exact initial version.</p><dl><dt>Owner</dt><dd>{short(owner)}</dd><dt>Network</dt><dd>Monad Testnet</dd><dt>Memory</dt><dd>Empty</dd><dt>Assistant access</dt><dd>None</dd><dt>Service</dt><dd className="pm-break">{location.origin}</dd></dl><button className="pm-button pm-primary" disabled={!!busy} onClick={() => run('Review the setup in your wallet…', stage)}>Sign project setup</button><button className="pm-button" disabled={!!busy} onClick={() => setDraft(null)}>Back</button><details><summary>What am I signing?</summary><p>A checkpoint tied to your wallet, this project, this service, and the registry below. A separate transaction confirmation follows.</p><code className="pm-break">{draft.genesis.checkpoint.controlDigest}</code><code className="pm-break">{settings.domain.verifyingContract}</code></details></> : <>
        <span className="pm-tag">Wallet connected · {short(owner)}</span><h2>Give your context a home.</h2><label>Project name<input value={name} maxLength={80} onChange={e => setName(e.target.value)} placeholder="My project"/></label><p className="pm-onboard-hint">The name is saved in this browser. It is not published onchain.</p><button className="pm-button pm-primary" disabled={!!busy || !name.trim()} onClick={() => run('Preparing your review…', async () => {await walletAccount(wallet, owner); setDraft({genesis: buildGenesis(settings, owner)});})}>Review project setup</button>
      </>}
      {owner && !ready && <details className="pm-recover"><summary>Already have a project?</summary><label>Project ID<input value={recovery} onChange={e => setRecovery(e.target.value)} placeholder="0x…" spellCheck="false"/></label><p>Find this ID in your saved project receipt. Reconnect on the same service with the owning wallet.</p><button className="pm-button" disabled={!!busy || !recovery.trim()} onClick={() => run('Recovering project…', recover)}>Recover project</button></details>}
      {owner && <button className="pm-onboard-disconnect" disabled={!!busy} onClick={() => {generation.current++; setOwner(''); setDraft(null); setResult(null); setError(''); setNotice('');}}>Disconnect from this page</button>}
    </section></main><footer className="pm-onboard-footer">Portable Memory <span>Context travels. You decide what stays.</span></footer></div>;
}

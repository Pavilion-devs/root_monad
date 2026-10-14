import React, { useEffect, useRef, useState } from 'react';
import { api, explain } from './api.js';
import './dashboard.css';

const short = text => text ? `${text.slice(0, 8)}…${text.slice(-6)}` : '—';
const kindLabel = kind => ({decision: 'Accepted decision', observation: 'Accepted observation', open_question: 'Open question'}[kind] || kind);
const views = ['Overview', 'Memory', 'Review', 'Connected apps', 'Settings'];
const paths = ['overview', 'memory', 'review', 'apps', 'settings'];
const titleFor = path => views[paths.indexOf(path)] || 'Overview';

function Icon({name, size = 20}) {
  const shapes = {
    Overview: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
    Memory: <><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6M9 12h6M9 16h4"/></>,
    Review: <><path d="M9 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-4M14 3l7 7M10 14l-1 4 4-1L22 8l-3-3z"/></>,
    'Connected apps': <><rect x="2" y="4" width="7" height="7" rx="2"/><rect x="15" y="13" width="7" height="7" rx="2"/><path d="M9 7h5a4 4 0 0 1 4 4v2M15 17h-5a4 4 0 0 1-4-4v-2"/></>,
    Settings: <><circle cx="12" cy="12" r="3"/><path d="m10 3 4 0 1 3 3 1 3 3v4l-3 1-1 3-3 3h-4l-1-3-3-1-3-3v-4l3-1 1-3z"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5 7a8 8 0 0 1 14-1l1 6M4 12l1 6a8 8 0 0 0 14-1"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name] || shapes.Memory}</svg>;
}

function Brand() {
  return <a className="pm-brand" href="/" aria-label="Portable Memory home"><span className="pm-brandmark"><svg width="23" height="23" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m4 9 8-5 8 5-8 5-8-5Zm0 5 8 5 8-5M4 18l8 5 8-5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg></span><span>Portable<span className="pm-brand-light">Memory</span></span></a>;
}

function Modal({title, children, close, busy = false}) {
  const ref = useRef();
  useEffect(() => { ref.current.showModal(); const el = ref.current; return () => el.close(); }, []);
  return <dialog className="pm-modal" ref={ref} onCancel={e => { e.preventDefault(); if (!busy) close(); }} aria-labelledby="pm-dialog-title"><div className="pm-modal-head"><h2 id="pm-dialog-title">{title}</h2><button className="pm-icon-button" disabled={busy} onClick={close} aria-label="Close dialog"><Icon name="close"/></button></div>{children}</dialog>;
}

function SourceList({sources, ids}) {
  const selected = sources.filter(s => ids.includes(s.id));
  return <details className="pm-sources"><summary>{selected.length} source{selected.length !== 1 ? 's' : ''} · view provenance</summary>{selected.map(s => <div className="pm-source" key={s.id}><span>{s.speaker || s.kind}</span><blockquote>{s.excerpt}</blockquote><code>{s.id}</code>{s.locator && <p>{s.locator}</p>}</div>)}</details>;
}

function RecordCard({record, sources, historical = false}) {
  return <article className="pm-record"><div className="pm-record-top"><span className={`pm-tag ${record.kind === 'observation' ? 'pm-tag-neutral' : ''}`}>{historical ? record.disposition : kindLabel(record.kind)}</span><span className="pm-record-proof"><Icon name="check" size={14}/> {historical ? 'Verified history' : 'Owner accepted'}</span></div><p className="pm-record-content">{record.content}</p>{record.replaces && <p className="pm-replacement">Replaces an earlier record · {short(record.replaces)}</p>}<SourceList sources={sources} ids={record.sourceIds}/><details className="pm-record-id"><summary>Verification details</summary><code>Record {record.id}</code><code>Author {record.author}</code></details></article>;
}

function Empty({title, children, icon = 'Memory', action}) {
  return <div className="pm-empty"><span className="pm-empty-icon"><Icon name={icon} size={28}/></span><h2>{title}</h2><p>{children}</p>{action}</div>;
}

export default function Dashboard() {
  const [view, setView] = useState(titleFor(location.pathname.split('/')[2]));
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState('Verifying your workspace…');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [code, setCode] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [history, setHistory] = useState(false);
  const [review, setReview] = useState(null);
  const [guide, setGuide] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [menu, setMenu] = useState(false);
  const inFlight = useRef(false);

  function navigate(next) {
    setView(next); setMenu(false);
    window.history.pushState({}, '', '/app/' + paths[views.indexOf(next)]);
  }
  useEffect(() => {
    document.title = 'Workspace · Portable Memory';
    const listener = () => setView(titleFor(location.pathname.split('/')[2]));
    window.addEventListener('popstate', listener);
    const params = new URLSearchParams(location.hash.slice(1));
    const pair = params.get('connect');
    if (pair) window.history.replaceState({}, '', location.pathname);
    run('Verifying your workspace…', async () => {
      if (pair) { await api('unlock', {code: pair}); setConnected(true); }
      await refresh();
    });
    return () => window.removeEventListener('popstate', listener);
  }, []);

  async function refresh() {
    setData(null);
    try {
      const result = await api('workspace');
      setData(result); setConnected(true); setUncertain(result.pendingCommit);
    } catch (error) {
      // The companion authenticates before returning workspace conflicts/outages.
      // Keep Refresh available instead of asking for a consumed pairing code.
      if ([409, 503].includes(error.status)) setConnected(true);
      throw error;
    }
  }
  async function run(label, work) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(label); setError(''); setNotice('');
    try { await work(); }
    catch (e) {
      setError(e.message === 'CONNECT_REQUIRED' ? '' : explain(e));
      if (['BASE_CONFLICT', 'AUTHORITY_UNAVAILABLE', 'CONTENT_UNAVAILABLE', 'STALE_CONTEXT', 'INTEGRITY_FAILURE', 'CONTENT_MISMATCH'].includes(e.message)) setData(null);
      if (['CONNECT_REQUIRED', 'PAIRING_EXPIRED', 'COMPANION_REQUIRED'].includes(e.message)) { setConnected(false); setData(null); }
      if (['RESUME_REQUIRED', 'COMMIT_PENDING'].includes(e.message)) setUncertain(true);
    }
    finally { inFlight.current = false; setBusy(''); }
  }
  async function prepare(action, target) {
    await run('Preparing the exact change…', async () => { setReview(await api('review', {action, target})); });
  }
  async function confirm() {
    await run('Signing and verifying your change…', async () => {
      const saved = review;
      setUncertain(true);
      let result;
      try { result = await api('confirm', {action: saved.action, target: saved.target, confirmation: saved.confirmation}); }
      finally { setReview(null); setData(null); }
      if (!result.verified) throw new Error('COMMIT_PENDING');
      setUncertain(false);
      await refresh();
      setNotice(`Change verified at revision ${result.sequence}.${result.reportWarning ? ' ' + result.reportWarning : ''}`);
    });
  }
  const pending = data?.proposals.filter(p => p.status === 'pending') || [];
  const apps = data?.applications || [];
  const active = apps.filter(a => a.status === 'active');
  const records = (history ? data?.history : data?.records) || [];
  const filtered = records.filter(r => (filter === 'all' || r.kind === filter) && r.content.toLowerCase().includes(query.toLowerCase()));
  const name = address => apps.find(a => a.address === address)?.name || short(address);

  return <div className="pm-shell">
    <aside className={`pm-sidebar ${menu ? 'pm-sidebar-open' : ''}`}>
      <Brand/>
      <div className="pm-project"><span className="pm-project-icon">P</span><div><strong>Project workspace</strong><small>{data ? short(data.projectId) : 'Owner companion'}</small></div></div>
      <p className="pm-nav-label">WORKSPACE</p>
      <nav aria-label="Workspace">{views.map(item => <button key={item} className={`pm-nav-item ${view === item ? 'pm-active' : ''}`} aria-current={view === item ? 'page' : undefined} onClick={() => navigate(item)}><Icon name={item}/>{item}{item === 'Review' && pending.length > 0 && <span className="pm-count">{pending.length}</span>}</button>)}</nav>
      <div className="pm-sidebar-bottom"><div className="pm-ownership"><Icon name="lock"/><div><strong>Your context. Your say.</strong><p>Apps suggest. You decide.</p></div></div><button className="pm-nav-item" onClick={() => setGuide(true)}><Icon name="arrow"/>Connection guide</button><a className="pm-back" href="/">← Back to website</a></div>
    </aside>
    <div className="pm-workspace">
      <header className="pm-topbar"><div className="pm-breadcrumb"><button className="pm-mobile-menu pm-icon-button" aria-label="Toggle navigation" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button><span>Workspace</span><span>/</span><strong>{view}</strong></div><div className="pm-top-actions"><span className="pm-environment">{data?.mode === 'hosted' ? 'Monad testnet' : data?.mode === 'demo' ? 'Sample workspace' : data ? 'Local signed log' : 'Local companion'}</span>{connected && <button className="pm-icon-button" title="Disconnect this browser" aria-label="Disconnect this browser" disabled={!!busy} onClick={() => run('Disconnecting…', async () => { await api('lock', {}); setConnected(false); setData(null); })}><Icon name="lock"/></button>}<span className="pm-avatar">You</span></div></header>
      <main className="pm-main" aria-busy={!!busy}>
        <div className="pm-page-heading"><div><p className="pm-eyebrow">A LITTLE CONTEXT GOES A LONG WAY</p><h1>{view === 'Overview' ? <>Pick up where you <em>left off.</em></> : view === 'Memory' ? <>A memory that <em>travels.</em></> : view === 'Review' ? <>You have the <em>final say.</em></> : view === 'Connected apps' ? <>Your tools. <em>Connected.</em></> : <>Make it <em>yours.</em></>}</h1><p>{view === 'Overview' ? 'The decisions, details, and open questions your next assistant should know.' : view === 'Memory' ? 'Accepted context, with its sources and history kept close.' : view === 'Review' ? 'See exactly what an assistant wants to remember before it becomes shared context.' : view === 'Connected apps' ? 'Know which assistants can read your context and suggest changes.' : 'Your project, verification, and recovery information.'}</p></div>{connected && <button className="pm-button pm-secondary" disabled={!!busy} onClick={() => run('Checking the latest accepted revision…', refresh)}><Icon name="refresh" size={16}/>Refresh</button>}</div>
        {error && <div className="pm-alert pm-alert-error" role="alert">{error}</div>}
        {notice && <div className="pm-alert pm-alert-success" role="status"><Icon name="check"/>{notice}</div>}
        {uncertain && <div className="pm-alert pm-alert-pending"><div><strong>A confirmed change needs checking</strong><p>We will check or resend the exact saved request. A new approval will not be created.</p></div><button className="pm-button" disabled={!!busy} onClick={() => run('Checking your saved change…', async () => { const r = await api('resume', {}); if (!r.verified) throw new Error('COMMIT_PENDING'); setUncertain(false); await refresh(); setNotice(`Change verified at revision ${r.sequence}.`); })}>Check pending change</button></div>}
        {busy && <div className="pm-progress" role="status"><span className="pm-spinner"/>{busy}<small>Verification may take a few moments.</small></div>}
        {!connected && !busy && <div className="pm-connect-card"><div className="pm-connect-art"><Icon name="Connected apps" size={56}/><span className="pm-tag">OWNER WORKSPACE</span></div><div><h2>Bring your context into view.</h2><p>Connect this browser to the companion running on your computer. It keeps your signing key local and verifies your memory before displaying it.</p><form onSubmit={e => { e.preventDefault(); run('Connecting your browser…', async () => { await api('unlock', {code: code.trim()}); setConnected(true); setCode(''); await refresh(); }); }}><label htmlFor="pair-code">Private connection code</label><input id="pair-code" type="password" value={code} onChange={e => setCode(e.target.value)} autoComplete="off" placeholder="Paste the code from your companion" required/><button className="pm-button" type="submit">Connect workspace <Icon name="arrow" size={16}/></button></form><button className="pm-text-button" onClick={() => setGuide(true)}>How do I start the companion?</button><p className="pm-small">This first version opens an existing project. Public account creation is not available yet.</p></div></div>}
        {data && <>
          {data.mode === 'demo' && <div className="pm-alert pm-alert-pending">Isolated sample workspace · illustrative records · no model or blockchain calls.</div>}
          {view === 'Overview' && <>
            <div className="pm-stats"><div><span className="pm-stat-icon"><Icon name="Memory"/></span><p>Accepted memories<strong>{data.records.length}</strong></p></div><button onClick={() => navigate('Review')}><span className="pm-stat-icon"><Icon name="Review"/></span><p>Awaiting review<strong>{pending.length}<small>{pending.length ? 'your call' : 'all caught up'}</small></strong></p><Icon name="arrow"/></button><button onClick={() => navigate('Connected apps')}><span className="pm-stat-icon"><Icon name="Connected apps"/></span><p>Active connections<strong>{active.length}</strong></p><Icon name="arrow"/></button></div>
            <div className="pm-overview-grid"><div><div className="pm-section-heading"><h2>What carries forward</h2><button className="pm-text-button" onClick={() => navigate('Memory')}>View all <Icon name="arrow" size={16}/></button></div>{data.records.length ? data.records.slice(0, 3).map(r => <RecordCard key={r.id} record={r} sources={data.sources}/>) : <Empty title="Your context starts here">Ask a connected assistant to propose a project decision. It will appear in Review for you to accept.</Empty>}</div><aside className="pm-context-aside"><div className="pm-handoff"><span className="pm-eyebrow">YOUR NEXT CONVERSATION</span><h2>Less explaining.<br/><em>More continuing.</em></h2><p>Open a connected assistant and ask:</p><blockquote>“Read our project memory. What have we decided, and what is still unresolved?”</blockquote><button className="pm-button pm-secondary" onClick={() => setGuide(true)}>Open connection guide <Icon name="arrow" size={15}/></button><p className="pm-small">Your assistant needs the memory integration enabled.</p></div><div className="pm-verification"><Icon name="check"/><div><strong>Revision {data.sequence} verified</strong><p>{data.authority === 'signed_log' ? 'Owner signature checked locally.' : 'Owner signature and Monad state checked.'}</p><small>As of {new Date(data.verifiedAt * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}. Refresh for changes.</small></div></div></aside></div>
          </>}
          {view === 'Memory' && <><div className="pm-toolbar"><div className="pm-search"><Icon name="search" size={18}/><input aria-label="Search memories" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find something worth remembering…"/></div><select aria-label="Memory type" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All types</option><option value="decision">Decisions</option><option value="observation">Observations</option><option value="open_question">Open questions</option></select></div><div className="pm-tabs"><button className={!history ? 'pm-selected' : ''} onClick={() => setHistory(false)}>Current context <span>{data.records.length}</span></button><button className={history ? 'pm-selected' : ''} onClick={() => setHistory(true)}>Earlier versions <span>{data.history.length}</span></button></div>{filtered.length ? <div className="pm-memory-grid">{filtered.map(r => <RecordCard key={r.id} record={r} sources={history ? data.historySources : data.sources} historical={history}/>)}</div> : <Empty title={query || filter !== 'all' ? 'No matching memories' : history ? 'Nothing has been replaced yet' : 'No accepted memories yet'}>{query || filter !== 'all' ? 'Try a different phrase or memory type.' : history ? 'Corrections and retractions will appear here, with their original sources.' : 'Suggestions appear in Review before they become shared context.'}</Empty>}</>}
          {view === 'Review' && <><div className="pm-section-heading"><h2>Awaiting your review <span className="pm-inline-count">{pending.length}</span></h2><span className="pm-small">Suggestions stay separate until accepted.</span></div>{pending.length ? pending.map(p => <article className="pm-proposal" key={p.id}><div className="pm-proposal-head"><span className="pm-app-avatar">{name(p.author).slice(0,1)}</span><div><strong>{name(p.author)}</strong><p>Suggested {p.records.length} record{p.records.length !== 1 ? 's' : ''}</p></div><span className={`pm-tag ${p.stale ? 'pm-tag-warning' : ''}`}>{p.stale ? 'Earlier revision' : 'Ready for review'}</span></div>{p.records.map(r => <div className="pm-proposed-record" key={r.id}><span className="pm-eyebrow">SUGGESTED {r.kind.replace('_', ' ')}</span><p>{r.content}</p></div>)}{p.retractions.length > 0 && <p>Requests removal of {p.retractions.length} current record(s). Review to see each change.</p>}<SourceList sources={p.sources} ids={p.records.flatMap(r => r.sourceIds)}/>{p.stale && <p className="pm-stale">The project has changed since this was proposed. Ask the author to submit a fresh proposal before accepting.</p>}<div className="pm-proposal-actions"><code>{short(p.id)}</code><button className="pm-button pm-secondary" disabled={!!busy || uncertain} onClick={() => prepare('reject', p.id)}>Review rejection</button><button className="pm-button" disabled={!!busy || uncertain || p.stale} onClick={() => prepare('approve', p.id)}>Review change <Icon name="arrow" size={16}/></button></div></article>) : <Empty title="You’re all caught up." icon="check">New suggestions from your connected assistants will appear here. Accepted decisions are ready for the next conversation.</Empty>}<details className="pm-resolved"><summary>Previously reviewed · {data.proposals.length - pending.length}</summary>{data.proposals.filter(p => p.status !== 'pending').map(p => <div key={p.id}><span className="pm-tag pm-tag-neutral">{p.status}</span><p>{p.records.map(r => r.content).join(' · ')}</p><small>{name(p.author)} · {short(p.id)}</small></div>)}</details></>}
          {view === 'Connected apps' && <><div className="pm-section-heading"><h2>Apps with a project identity</h2><button className="pm-button pm-secondary" onClick={() => setGuide(true)}>Connection guide <Icon name="arrow" size={16}/></button></div><div className="pm-app-grid">{apps.map(app => <article className="pm-app-card" key={app.address}><div className="pm-proposal-head"><span className="pm-app-avatar">{app.name.slice(0,1)}</span><div><h2>{app.name}</h2><p>{short(app.address)}</p></div><span className={`pm-tag ${app.status !== 'active' ? 'pm-tag-neutral' : ''}`}>{app.status}</span></div><div className="pm-permissions"><p><Icon name="Memory" size={16}/>{app.rights.includes('read_current') ? 'Can read current context' : 'No current read grant'}</p><p><Icon name="Review" size={16}/>{app.rights.includes('propose') ? 'Can suggest changes' : 'Cannot suggest changes'}</p><p><Icon name="lock" size={16}/>Cannot accept owner decisions</p></div>{app.expiresAt && <p className="pm-small">Grant expires {new Date(Number(app.expiresAt)*1000).toLocaleString()}</p>}<details className="pm-record-id"><summary>Application identity</summary><code>{app.address}</code></details><button className="pm-text-button pm-danger" disabled={!!busy || uncertain || app.status === 'removed'} onClick={() => prepare('revoke', app.address)}>Review removal of access</button></article>)}</div><p className="pm-footnote">Active means the grant is valid, not that an assistant is online. Removing access blocks future requests through the service; it cannot erase information already retrieved.</p></>}
          {view === 'Settings' && <div className="pm-settings"><section className="pm-settings-panel"><h2>Project & verification</h2><dl><dt>Project</dt><dd><code>{data.projectId}</code></dd><dt>Owner</dt><dd><code>{data.owner}</code></dd><dt>Authority</dt><dd>{data.authority === 'signed_log' ? 'Local owner-signed log · no blockchain calls' : 'Monad testnet · finalized state verification'}</dd><dt>Accepted revision</dt><dd>{data.sequence}</dd><dt>Checkpoint</dt><dd><code>{data.checkpoint}</code></dd></dl><p className="pm-small">Signatures establish who accepted the content. They do not establish that every statement is true.</p></section><section className="pm-settings-panel"><h2>Privacy & recovery</h2><p>Your owner key stays in the companion on your computer. Memory content is stored encrypted, but the memory service decrypts it for authorized applications.</p><p>This browser session lasts up to eight hours. Disconnect it using the lock button above.</p><h3>Exports and provider migration</h3><p>Protected export, restore, and migration currently use the operator tools. They are not wired to this dashboard yet. Recovery keys must be kept separately from encrypted archives.</p><p className="pm-small">Consult RECOVERY_MIGRATION.md and HOSTING.md in the project before a recovery operation. An older backup must not replace newer accepted state.</p></section></div>}
          <footer className="pm-workspace-footer"><span><Icon name="lock" size={13}/>Owner-controlled context</span><span>Revision {data.sequence} · verified on refresh</span></footer>
        </>}
        {connected && !data && !busy && <Empty title="Let’s verify your workspace again" action={<button className="pm-button" onClick={() => run('Verifying your workspace…', refresh)}>Try again</button>}>We won’t present an unverified or incomplete response as your current memory.</Empty>}
      </main>
    </div>
    {review && <Modal title={review.action === 'revoke' ? 'Remove this app’s access?' : review.action === 'reject' ? 'Reject this suggestion?' : 'Review this change'} close={() => setReview(null)} busy={!!busy}>{error && <div className="pm-alert pm-alert-error" role="alert">{error}</div>}<div className="pm-review-meta"><span className="pm-tag">Revision {review.fromSequence} → {review.toSequence}</span><span>Expires {new Date(Number(review.expiresAtUnix)*1000).toLocaleTimeString()}</span></div>{review.proposal ? <><p className="pm-small">Proposed by {name(review.proposal.author)}. Acceptance preserves each record’s stated type.</p>{review.proposal.replacements.map(r => <div className="pm-diff pm-diff-before" key={r.id}><span>REPLACING</span><p>{r.currentRecord?.content || r.id}</p></div>)}{review.proposal.retractions.map(r => <div className="pm-diff pm-diff-before" key={r.id}><span>RETRACTING</span><p>{r.currentRecord?.content || r.id}</p></div>)}{review.proposal.records.map(r => <div className="pm-diff" key={r.id}><span>{r.kind.replace('_', ' ').toUpperCase()}</span><p>{r.content}</p></div>)}<SourceList sources={review.referencedSourcesInReview} ids={review.proposal.records.flatMap(r => r.sourceIds)}/></> : <><h3>{name(review.target)}</h3><code className="pm-break">{review.target}</code><p>This app will lose its grant to this project. Information it already retrieved cannot be erased.</p></>}<p className="pm-review-effect">{review.effect}</p><details className="pm-record-id"><summary>Exact change to be signed</summary><code>{review.confirmation}</code></details><div className="pm-modal-actions"><button className="pm-button pm-secondary" disabled={!!busy} onClick={() => setReview(null)}>Go back</button><button className="pm-button" disabled={!!busy || uncertain} onClick={confirm}>{busy ? 'Verifying…' : review.action === 'approve' ? 'Accept this change' : review.action === 'reject' ? 'Confirm rejection' : 'Remove access'}</button></div></Modal>}
    {guide && <Modal title="Connect your workspace" close={() => setGuide(false)}><p>This first dashboard uses a local companion with your existing project. It does not create a public account or new app grant.</p><h3>1. Start the companion</h3><p>From your portable-memory folder, use the existing hosted testnet project:</p><pre>.venv/bin/python ops/dashboard.py --hosted</pre><p>Or use an already running developer-kit workspace:</p><pre>.mcp-venv/bin/python ops/dashboard.py --state /path/to/workspace</pre><p>Open the private link it prints. The one-use connection code expires after 20 minutes; keep it private.</p><h3>2. Open your connected assistant</h3><p>For the existing hosted project, use the configured launcher:</p><pre>.venv/bin/python integrations/codex/chat.py --allow-proposals</pre><p>The Claude launcher and its model credentials are documented in CLAUDE_CODE_INTEGRATION.md. For a local developer-kit project, use the generated connection files in its connections folder.</p><h3>3. Carry a decision forward</h3><p>Ask the assistant to read project memory, then propose a decision. Review it here. Open the other configured assistant and ask it to read the latest accepted context.</p><p className="pm-small">New app identities and grants still use setup tools. Buttons here never silently grant access.</p></Modal>}
  </div>;
}

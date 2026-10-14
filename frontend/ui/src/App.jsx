import React, { useEffect, useRef, useState } from 'react';
import { mountScene } from './scene.js';

function Typed({ as: Tag = 'span', text, delay, step, ...props }) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const [visible, setVisible] = useState(reducedMotion ? text : '');

  useEffect(() => {
    if (reducedMotion) return;
    let index = 0;
    let nextTick;
    const tick = () => {
      index += 1;
      setVisible(text.slice(0, index));
      if (index < text.length) nextTick = window.setTimeout(tick, step);
    };
    nextTick = window.setTimeout(tick, delay);
    return () => window.clearTimeout(nextTick);
  }, [text, delay, step, reducedMotion]);

  return <Tag {...props}>{visible}</Tag>;
}

export default function App() {
  const sceneRef = useRef(null);
  const [audience, setAudience] = useState('people');
  const [openFaq, setOpenFaq] = useState(0);

  useEffect(() => {
    document.body.classList.add('is-loaded');
    let unmountScene = () => {};
    try {
      unmountScene = mountScene(sceneRef.current);
    } catch (error) {
      console.error('Unable to start the 3D scene:', error);
      document.documentElement.classList.add('no-module');
    }

    const reveals = [...document.querySelectorAll('[data-reveal]')];
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in');
          observer.unobserve(entry.target);
        }
      }
    }, { threshold: 0.08, rootMargin: '0px 0px -10% 0px' });
    reveals.forEach(element => observer.observe(element));

    return () => {
      unmountScene();
      observer.disconnect();
      document.body.classList.remove('is-loaded');
      document.documentElement.classList.remove('no-module');
    };
  }, []);

  return (
    <>
    <div className="bg-sheen" />
    <canvas id="scene" ref={sceneRef} aria-hidden="true" />
    <nav className="nav">
      <a className="brand" href="#hero">
        <svg width="26" height="18" viewBox="0 0 26 18" fill="none" aria-hidden="true">
          <path d="M1 13.5 L5.2 4.5 L9 11 L13 1.5 L17 11 L20.8 4.5 L25 13.5" stroke="#141416" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" fill="none">
          </path>
          <circle cx="5.2" cy="15.6" r="1.5" fill="#141416">
          </circle>
          <circle cx="13" cy="15.6" r="1.5" fill="#141416">
          </circle>
          <circle cx="20.8" cy="15.6" r="1.5" fill="#141416">
          </circle>
        </svg>
        
    Portable Memory
  
      </a>
      <ul className="nav-links">
        <li>
          <a href="#showcase">
            Platform
          </a>
        </li>
        <li>
          <a href="#testimonials">
            Ownership
          </a>
        </li>
        <li>
          <a href="#gallery">
            Inside
          </a>
        </li>
        <li>
          <a href="#timeline">
            How it works
          </a>
        </li>
        <li>
          <a href="#pricing">
            Get started
          </a>
        </li>
      </ul>
      <button className="signin" type="button" onClick={() => location.assign("/app")}>
        Open workspace
      </button>
    </nav>
    <main>
      <section className="hero" id="hero">
        <div className="hero-sub">
          <Typed className="tline" text="Keep the context that matters" delay={900} step={30} />
          <Typed className="tline" text="across your AI assistants" delay={2100} step={30} />
        </div>
        <h1 className="hero-title">
          <Typed className="tline" text="Keep your context" delay={400} step={52} />
          <span className="tline serif">
            <Typed text={'keep\u00a0'} delay={1500} step={52} />
            <Typed as="em" className="accent" text="Creating" delay={1800} step={52} />
          </span>
        </h1>
        <div className="scroll-cue">
          <span>
            SCROLL DOWN
          </span>
          <svg width="22" height="20" viewBox="0 0 22 20" fill="none" aria-hidden="true">
            <path d="M2 5 L6 1.5 L11 5 L16 1.5 L20 5 L11 18.5 Z M2 5 L11 9.5 L20 5" stroke="#55555c" strokeWidth="1.3" strokeLinejoin="round" fill="none">
            </path>
          </svg>
        </div>
      </section>
      <section className="section" id="features">
        <div className="section-head" data-reveal="">
          <h2 className="section-title">
            Key 
            <span className="serif">
              benefits
            </span>
            <br />
            of our app
          </h2>
        </div>
        <div className="cards">
          <article className="card" data-reveal="" style={{"--d": ".22s"}}>
            <div className="icon-tile">
              <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden="true">
                <path d="M22 5.5 L35.5 13.2 V28.8 L22 36.5 L8.5 28.8 V13.2 Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
                </path>
                <circle cx="22" cy="21" r="5.2" stroke="currentColor" strokeWidth="2">
                </circle>
              </svg>
            </div>
            <h3>
              Context That Travels
            </h3>
            <p>
              Carry accepted project decisions,
              <br />
              sources, and open questions
            </p>
          </article>
          <article className="card" data-reveal="">
            <div className="icon-tile">
              <svg width="46" height="46" viewBox="0 0 46 46" fill="none" aria-hidden="true">
                <circle cx="23" cy="17" r="5" stroke="currentColor" strokeWidth="2">
                </circle>
                <path d="M14.5 34 C14.5 28.8 18.2 25.5 23 25.5 C27.8 25.5 31.5 28.8 31.5 34" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                </path>
                <path d="M12.5 20.5 C10.3 20.2 8.6 18.4 8.6 16 C8.6 13.5 10.6 11.5 13.1 11.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                </path>
                <path d="M6.5 31 C6.5 27.4 9 24.9 12.4 24.9" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                </path>
                <path d="M33.5 20.5 C35.7 20.2 37.4 18.4 37.4 16 C37.4 13.5 35.4 11.5 32.9 11.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                </path>
                <path d="M39.5 31 C39.5 27.4 37 24.9 33.6 24.9" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                </path>
              </svg>
            </div>
            <h3>
              Your Final Say
            </h3>
            <p>
              Review what your assistant suggests,
              <br />
              then choose what carries forward
            </p>
          </article>
          <article className="card" data-reveal="" style={{"--d": ".40s"}}>
            <div className="icon-tile">
              <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden="true">
                <circle cx="20" cy="20" r="10.5" stroke="currentColor" strokeWidth="2">
                </circle>
                <path d="M28 28 L36 36" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                </path>
              </svg>
            </div>
            <h3>
              Verifiable History
            </h3>
            <p>
              Trace a memory back to its source
              <br />
              and the revision you accepted
            </p>
          </article>
        </div>
      </section>
      <section className="section" id="showcase">
        <div className="section-head" data-reveal="">
          <h2 className="section-title">
            One shared context
            <br />
            for the work you 
            <span className="serif">
              continue
            </span>
          </h2>
          <p className="section-sub">
            Decisions, sources, and corrections travel together. The same accepted context can be retrieved by your next connected assistant.
          </p>
        </div>
        <div className="showcase-panel" data-reveal="" style={{"--d": ".18s"}}>
          <div className="app">
            <div className="app-bar">
              <i className="dot">
              </i>
              <i className="dot">
              </i>
              <i className="dot">
              </i>
              <span className="title">
                portable memory / project · illustrative workflow
              </span>
            </div>
            <aside className="app-side">
              <div className="side-item on">
                <i>
                </i>
                Overview
              </div>
              <div className="side-item">
                <i>
                </i>
                Memory
              </div>
              <div className="side-item">
                <i>
                </i>
                Review
              </div>
              <div className="side-item">
                <i>
                </i>
                History
              </div>
              <div className="side-item">
                <i>
                </i>
                Apps
              </div>
              <div className="side-item">
                <i>
                </i>
                Settings
              </div>
            </aside>
            <div className="app-main">
              <div>
                <div className="col-head">
                  <span>
                    SUGGESTED
                  </span>
                  <span>
                    8
                  </span>
                </div>
                <div className="tile">
                  <span className="chip">
                    DECISION
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
                <div className="tile">
                  <span className="chip">
                    SOURCE
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
                <div className="tile grad">
                  <span className="chip">
                    QUESTION
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
              </div>
              <div>
                <div className="col-head">
                  <span>
                    IN REVIEW
                  </span>
                  <span>
                    3
                  </span>
                </div>
                <div className="tile grad">
                  <span className="chip">
                    REVIEW
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
                <div className="tile grad2">
                  <span className="chip">
                    CONTEXT
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
              </div>
              <div>
                <div className="col-head">
                  <span>
                    ACCEPTED
                  </span>
                  <span>
                    12
                  </span>
                </div>
                <div className="tile grad2">
                  <span className="chip">
                    DECISION
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
                <div className="tile">
                  <span className="chip">
                    SOURCE
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
                <div className="tile grad">
                  <span className="chip">
                    HISTORY
                  </span>
                  <div className="bar">
                  </div>
                  <div className="bar">
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="section" id="gallery">
        <div className="section-head" data-reveal="">
          <h2 className="section-title">
            A closer 
            <span className="serif">
              look
            </span>
            <br />
            at the workspace
          </h2>
        </div>
        <div className="gallery">
          <figure className="shot big g1" data-reveal="">
            <img src="/previews/overview.svg" alt="Illustrative Portable Memory overview view" loading="lazy" decoding="async" />
            <span>
              OVERVIEW
            </span>
          </figure>
          <figure className="shot g2" data-reveal="" style={{"--d": ".10s"}}>
            <img src="/previews/memory.svg" alt="Illustrative Portable Memory memory view" loading="lazy" decoding="async" />
            <span>
              MEMORY
            </span>
          </figure>
          <figure className="shot g3" data-reveal="" style={{"--d": ".20s"}}>
            <img src="/previews/review.svg" alt="Illustrative Portable Memory review view" loading="lazy" decoding="async" />
            <span>
              REVIEW
            </span>
          </figure>
          <figure className="shot g4" data-reveal="" style={{"--d": ".30s"}}>
            <img src="/previews/apps.svg" alt="Illustrative Portable Memory connected apps view" loading="lazy" decoding="async" />
            <span>
              CONNECTED APPS
            </span>
          </figure>
          <figure className="shot g5" data-reveal="" style={{"--d": ".40s"}}>
            <img src="/previews/history.svg" alt="Illustrative Portable Memory history view" loading="lazy" decoding="async" />
            <span>
              HISTORY
            </span>
          </figure>
        </div>
      </section>
      <section className="section" id="timeline">
        <div className="section-head" data-reveal="">
          <h2 className="section-title">
            How your context 
            <span className="serif">
              travels
            </span>
            <br />
            between assistants
          </h2>
          <p className="section-sub">
            One project. Two assistants. An owner who decides what becomes shared memory.
          </p>
        </div>
        <div className="timeline">
          <div className="step on" data-reveal="">
            <em>
              01
            </em>
            <h4>
              Connect
            </h4>
            <p>
              Connect a supported assistant to a project with permission to read and propose.
            </p>
          </div>
          <div className="step" data-reveal="" style={{"--d": ".12s"}}>
            <em>
              02
            </em>
            <h4>
              Capture
            </h4>
            <p>
              Ask your assistant to propose useful context with its source and stated type.
            </p>
          </div>
          <div className="step" data-reveal="" style={{"--d": ".24s"}}>
            <em>
              03
            </em>
            <h4>
              Review
            </h4>
            <p>
              Review the exact change. Your acceptance makes it part of shared project context.
            </p>
          </div>
          <div className="step" data-reveal="" style={{"--d": ".36s"}}>
            <em>
              04
            </em>
            <h4>
              Continue
            </h4>
            <p>
              Open another connected assistant and retrieve the latest accepted revision.
            </p>
          </div>
        </div>
      </section>
      <section className="section" id="pricing">
        <div className="section-head" data-reveal="">
          <h2 className="section-title">A place to <span className="serif">begin</span><br/>and build from</h2>
          <div className="toggle" role="group" aria-label="Getting started audience">
            <button className={audience === 'people' ? 'on' : ''} aria-pressed={audience === 'people'} onClick={() => setAudience('people')}>For people</button>
            <button className={audience === 'builders' ? 'on' : ''} aria-pressed={audience === 'builders'} onClick={() => setAudience('builders')}>For builders</button>
          </div>
        </div>
        <div className="plans">
          {[
            {title:'Explore', headline:'01', sub:'/ understand the flow', text:audience === 'people' ? 'See how useful context moves from a suggestion to an accepted decision.' : 'Follow the protocol from signed proposal to a verified accepted revision.', bullets:['Explicit acceptance','Sources alongside memory','Visible corrections'], button:'See the workflow', target:'#timeline'},
            {title:'Continue', headline:'02', sub:'/ open your project', text:audience === 'people' ? 'Review your context and carry it into your next connected assistant.' : 'Use the owner companion with an existing local or hosted testnet project.', bullets:['Owner review workspace','Scoped app permissions','Verified revision status','Interrupted-change recovery'], button:'Open workspace', target:'/app'},
            {title:'Build', headline:'03', sub:'/ connect your app', text:audience === 'people' ? 'Use the local developer kit to explore the workflow with isolated identities.' : 'Integrate through the protocol and MCP bridge using the local developer kit.', bullets:['Local evaluation kit','Read and propose through MCP','Documented trust boundaries'], button:'Read setup guide', target:'/setup.html'},
          ].map((plan,i) => <article className={`plan${i === 1 ? ' featured' : ''}`} data-reveal="" style={{'--d': i === 1 ? '0s' : `${(i+1)*.12}s`}} key={plan.title}>
            {i === 1 && <span className="badge">DEVELOPER PREVIEW</span>}<h3>{plan.title}</h3><div className="price"><b>{plan.headline}</b><i>{plan.sub}</i></div><p>{plan.text}</p>
            <ul>{plan.bullets.map(text => <li key={text}><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8.5 L6.5 12 L13 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>{text}</li>)}</ul>
            <button className="buy" onClick={() => location.assign(plan.target)}>{plan.button}</button>
          </article>)}
        </div>
      </section>
      <section className="section" id="testimonials">
        <div className="section-head" data-reveal=""><h2 className="section-title">Control that stays <span className="serif">with you</span></h2></div>
        <div className="quotes">
          {[
            ['01','Your acceptance','Owner authority','An assistant can suggest a change. Only the owner can accept it into the shared project state.'],
            ['02','Your context','Portable history','Accepted context carries its sources and corrections. Our reference providers support encrypted migration.'],
            ['03','Your permissions','Scoped connections','Decide which apps can read and propose. Revocation blocks future guarded access, not copies already retrieved.'],
          ].map(([number,title,sub,text],i) => <article className="quote" data-reveal="" style={{'--d':`${i*.12}s`}} key={number}><span className="mark">↗</span><p>{text}</p><div className="who"><span className="avatar" style={{background:'linear-gradient(140deg,#cfc6fb,#f8bfe9)'}}>{number}</span><div><b>{title}</b><small>{sub}</small></div></div></article>)}
        </div>
      </section>
      <section className="faq" id="faq">
        <div className="faq-head" data-reveal="">
          <h2 className="q-title">
            Still have
            <br />
            <span className="serif">
              unanswered
            </span>
             questions?
          </h2>
          <button className="q-arrow" onClick={() => document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" })} aria-label="Scroll to contact" type="button">
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
              <path d="M13 3 V22 M5.5 15 L13 22.5 L20.5 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              </path>
            </svg>
          </button>
        </div>
        <div className="faq-list" data-reveal="" style={{"--d": ".14s"}}>
          <div className={`faq-item${openFaq === 0 ? ' is-open' : ''}`}>
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === 0 ? -1 : 0)} aria-expanded={openFaq === 0} type="button">
              Which assistants can I connect?
              <span className="faq-sign">
              </span>
            </button>
            <div className="faq-a">
              <div>
                <p>
                  The current integrations support Claude Code and Codex through our MCP bridge and launchers. Setup uses the developer tools; public one-click onboarding is not available yet.
                </p>
              </div>
            </div>
          </div>
          <div className={`faq-item${openFaq === 1 ? ' is-open' : ''}`}>
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === 1 ? -1 : 1)} aria-expanded={openFaq === 1} type="button">
              Does an assistant decide what becomes memory?
              <span className="faq-sign">
              </span>
            </button>
            <div className="faq-a">
              <div>
                <p>
                  An assistant can propose a change. The owner reviews and accepts it. Observations stay observations, and unresolved questions remain visible.
                </p>
              </div>
            </div>
          </div>
          <div className={`faq-item${openFaq === 2 ? ' is-open' : ''}`}>
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === 2 ? -1 : 2)} aria-expanded={openFaq === 2} type="button">
              What does Monad verify?
              <span className="faq-sign">
              </span>
            </button>
            <div className="faq-a">
              <div>
                <p>
                  Monad testnet records commitments to accepted revisions and permissions. Clients check retrieved state against that reference. It verifies acceptance and ordering, not whether a statement is true.
                </p>
              </div>
            </div>
          </div>
          <div className={`faq-item${openFaq === 3 ? ' is-open' : ''}`}>
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === 3 ? -1 : 3)} aria-expanded={openFaq === 3} type="button">
              Who can read the memory content?
              <span className="faq-sign">
              </span>
            </button>
            <div className="faq-a">
              <div>
                <p>
                  Content stays offchain and is encrypted at rest. The memory service decrypts it for authorized apps. The service operator and any app receiving plaintext can read it; this is not end-to-end secrecy from the service.
                </p>
              </div>
            </div>
          </div>
          <div className={`faq-item${openFaq === 4 ? ' is-open' : ''}`}>
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === 4 ? -1 : 4)} aria-expanded={openFaq === 4} type="button">
              Can I change memory providers?
              <span className="faq-sign">
              </span>
            </button>
            <div className="faq-a">
              <div>
                <p>
                  Encrypted export and migration have been tested between our reference-provider instances. Compatibility with a separately implemented provider remains to be validated.
                </p>
              </div>
            </div>
          </div>
          <div className={`faq-item${openFaq === 5 ? ' is-open' : ''}`}>
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === 5 ? -1 : 5)} aria-expanded={openFaq === 5} type="button">
              What happens if a change is interrupted?
              <span className="faq-sign">
              </span>
            </button>
            <div className="faq-a">
              <div>
                <p>
                  Your confirmed request is saved before submission. Recovery checks the accepted state and can resend the exact request. The interface only reports success after verification.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="cta" id="cta">
        <div className="section-head" data-reveal="" style={{"marginBottom": "0"}}>
          <h2 className="section-title">
            Carry your
            <br />
            project 
            <span className="serif">
              context
            </span>
             today
          </h2>
          <p className="section-sub">
            A working developer preview. Connect your existing project and keep meaningful context close.
          </p>
          <div className="cta-actions">
            <button className="btn-dark" type="button" onClick={() => location.assign("/app")}>
              Open workspace
            </button>
            <button className="btn-ghost" type="button" onClick={() => document.getElementById("timeline").scrollIntoView({behavior:"smooth"})}>
              Explore the workflow
            </button>
          </div>
        </div>
      </section>
      <section className="contact" id="contact">
        <div className="ask-band">
          <h2>
            Keep your context close
          </h2>
          <a href="/app">
            Open your workspace ↗
          </a>
        </div>
        <div className="tags">
          <span className="tag">
            ACCELERATE
          </span>
          <span className="tag">
            ENHANCE
          </span>
          <span className="tag">
            AUTOMATE
          </span>
          <span className="tag">
            CREATE
          </span>
          <span className="tag">
            ENGAGE
          </span>
          <span className="tag">
            ANALYZE
          </span>
          <span className="tag">
            ITERATE
          </span>
        </div>
        <div className="foot">
          <small>
            Portable Memory · Developer preview · Monad testnet
          </small>
          <div className="socials">
            <span role="img" aria-label="Instagram template icon">
              <svg width="21" height="21" viewBox="0 0 24 24" fill="none">
                <rect x="2.5" y="2.5" width="19" height="19" rx="5.5" stroke="currentColor" strokeWidth="1.8">
                </rect>
                <circle cx="12" cy="12" r="4.4" stroke="currentColor" strokeWidth="1.8">
                </circle>
                <circle cx="17.6" cy="6.4" r="1.35" fill="currentColor">
                </circle>
              </svg>
            </span>
            <span role="img" aria-label="YouTube template icon">
              <svg width="24" height="18" viewBox="0 0 24 18" fill="none">
                <rect x="1" y="1" width="22" height="16" rx="4.5" stroke="currentColor" strokeWidth="1.8">
                </rect>
                <path d="M10 5.8 L15.2 9 L10 12.2 Z" fill="currentColor">
                </path>
              </svg>
            </span>
            <span role="img" aria-label="Google template icon">
              <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor">
                <path d="M21.6 12.2c0-.7-.06-1.4-.18-2H12v3.9h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.4Z" opacity=".9">
                </path>
                <path d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22Z" opacity=".7">
                </path>
                <path d="M6.4 14a6 6 0 0 1 0-3.9V7.5H3.1a10 10 0 0 0 0 9L6.4 14Z" opacity=".55">
                </path>
                <path d="M12 6c1.5 0 2.8.5 3.8 1.5L18.7 4.7A10 10 0 0 0 3.1 7.5L6.4 10c.8-2.3 3-4 5.6-4Z" opacity=".8">
                </path>
              </svg>
            </span>
            <span role="img" aria-label="LinkedIn template icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M4.98 3.5A2.5 2.5 0 1 1 0 3.5a2.5 2.5 0 0 1 4.98 0ZM.4 8.4h4.2V24H.4V8.4Zm7.6 0h4v2.1h.06c.56-1.05 1.93-2.16 3.97-2.16 4.25 0 5.03 2.8 5.03 6.44V24h-4.2v-8.1c0-1.93-.03-4.42-2.7-4.42-2.7 0-3.1 2.1-3.1 4.28V24H8V8.4Z" transform="translate(1.5 -1.5) scale(.88)">
                </path>
              </svg>
            </span>
            <span role="img" aria-label="Discord template icon">
              <svg width="24" height="18" viewBox="0 0 24 18" fill="currentColor">
                <path d="M20.3 1.6A19.6 19.6 0 0 0 15.5.1l-.6 1.2a18 18 0 0 0-5.8 0L8.5.1a19.6 19.6 0 0 0-4.8 1.5A20.3 20.3 0 0 0 .2 15.2 19.8 19.8 0 0 0 6.1 18l1.3-2a12.8 12.8 0 0 1-2-1l.5-.4a14 14 0 0 0 12.2 0l.5.4c-.64.38-1.32.71-2 1l1.3 2a19.8 19.8 0 0 0 5.9-2.9A20.2 20.2 0 0 0 20.3 1.6ZM8.3 12.3c-1.2 0-2.1-1.1-2.1-2.4S7.1 7.5 8.3 7.5s2.1 1.1 2.1 2.4-1 2.4-2.1 2.4Zm7.4 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.1 1.1 2.1 2.4-.9 2.4-2.1 2.4Z">
                </path>
              </svg>
            </span>
            <span role="img" aria-label="WeChat template icon">
              <svg width="24" height="20" viewBox="0 0 24 20" fill="currentColor">
                <path d="M9 1C4.6 1 1 3.9 1 7.4c0 2 1.1 3.7 2.9 4.9l-.7 2.2 2.6-1.3c.8.2 1.6.4 2.5.4h.5A6 6 0 0 1 8.6 12c0-3.3 3.2-5.9 7-5.9h.4C15.3 3.2 12.4 1 9 1ZM6.3 5.6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Zm5.4 0a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z">
                </path>
                <path d="M23 12.1c0-2.9-3-5.2-6.7-5.2s-6.7 2.3-6.7 5.2 3 5.2 6.7 5.2c.8 0 1.5-.1 2.2-.3l2.2 1.1-.6-1.9c1.7-1 2.9-2.5 2.9-4.1Zm-9-1a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Zm4.6 0a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Z">
                </path>
              </svg>
            </span>
          </div>
        </div>
      </section>
    </main>
    </>
  );
}

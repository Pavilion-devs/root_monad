import React, { lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const Page = lazy(() => location.pathname === '/start' ? import('./Onboarding.jsx') : location.pathname.startsWith('/app') ? import('./Dashboard.jsx') : import('./App.jsx'));
createRoot(document.getElementById('root')).render(<Suspense fallback={<p style={{padding: 40}}>Opening Portable Memory…</p>}><Page /></Suspense>);

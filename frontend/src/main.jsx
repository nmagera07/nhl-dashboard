import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import * as Sentry from '@sentry/react'
import './index.css'
import App from './App.jsx'
import ErrorFallback from './components/ErrorFallback.jsx'

// Error tracking (Sentry) is optional -- a missing VITE_SENTRY_DSN just
// means errors aren't reported anywhere, not a broken build. Sentry's
// exported functions (including the ErrorBoundary below) are safe
// no-ops before init() is called, so skipping this doesn't break
// anything, it just means nothing gets sent.
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || (import.meta.env.PROD ? 'production' : 'development'),
    // Real-user performance: Core Web Vitals, page loads, and every API
    // call's timing. Traffic is small enough to keep every trace for now.
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 1.0,
    // No sentry-trace/baggage headers on API calls: custom headers make
    // every cross-origin GET pay for a CORS preflight round trip first.
    tracePropagationTargets: [],
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={ErrorFallback}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Sentry.ErrorBoundary>
  </StrictMode>,
)

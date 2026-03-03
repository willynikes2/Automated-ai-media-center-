import { initSentry, Sentry } from './lib/sentry';
initSentry();

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

function ErrorFallback() {
  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center p-4">
      <div className="text-center space-y-4 max-w-md">
        <h1 className="text-2xl font-bold text-white">Something went wrong</h1>
        <p className="text-gray-400">
          An unexpected error occurred. Please try refreshing the page.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors"
        >
          Refresh Page
        </button>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root')!);

if (import.meta.env.VITE_SENTRY_DSN) {
  root.render(
    <React.StrictMode>
      <Sentry.ErrorBoundary fallback={<ErrorFallback />} showDialog>
        <App />
      </Sentry.ErrorBoundary>
    </React.StrictMode>
  );
} else {
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

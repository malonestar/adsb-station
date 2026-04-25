import { createRoot } from 'react-dom/client'
import { App } from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './styles/globals.css'

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('#root element not found')

// StrictMode intentionally removed — it double-invokes effects in dev, which
// can mask/cause spurious issues during diagnosis. Re-add once the app is
// stable if you want the extra checks back.
createRoot(rootEl).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
)

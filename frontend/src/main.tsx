import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { isBrowserDemo, startBrowserBackend } from './lib/browserBackend'
import './styles.css'

if (isBrowserDemo()) startBrowserBackend()

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)

if (!isBrowserDemo() && 'serviceWorker' in navigator && location.protocol !== 'capacitor:') {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => undefined) })
}

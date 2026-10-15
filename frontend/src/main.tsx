import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Health = { status: 'ok'; service: string; version: string }
type ApiState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: Health }
  | { kind: 'error' }

function App() {
  const [state, setState] = useState<ApiState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    let disposed = false
    setState({ kind: 'loading' })
    async function checkHealth() {
      try {
        const response = await fetch('/api/health', { signal: controller.signal })
        if (!response.ok) throw new Error('API request failed')
        const data: unknown = await response.json()
        if (typeof data !== 'object' || data === null ||
            !('status' in data) || data.status !== 'ok' ||
            !('service' in data) || typeof data.service !== 'string' ||
            !('version' in data) || typeof data.version !== 'string') {
          throw new Error('Unexpected API response')
        }
        if (!disposed) setState({ kind: 'ready', health: data as Health })
      } catch {
        if (!disposed) setState({ kind: 'error' })
      } finally {
        clearTimeout(timeout)
      }
    }
    void checkHealth()
    return () => { disposed = true; clearTimeout(timeout); controller.abort() }
  }, [attempt])

  return (
    <main>
      <p className="eyebrow">NFL · LOCAL WORKSPACE</p>
      <h1>A clearer view of game day.</h1>
      <p className="intro">Your NFL prediction dashboard starts here.</p>
      <section aria-labelledby="connection-title">
        <h2 id="connection-title">API connection</h2>
        <div role="status" aria-live="polite">
          {state.kind === 'loading' && <p>Checking connection…</p>}
          {state.kind === 'ready' && <>
            <p className="connected">● Connected</p>
            <p>{state.health.service} · v{state.health.version}</p>
          </>}
          {state.kind === 'error' && <>
            <p>API unavailable. Start the backend, then retry.</p>
            <button onClick={() => setAttempt(value => value + 1)}>Retry connection</button>
          </>}
        </div>
      </section>
      <p className="note">Setup stage · No datasets or predictions loaded yet.</p>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)

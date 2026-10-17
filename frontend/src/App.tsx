import { useEffect, useState } from 'react'
import './App.css'

type BackendStatus =
  | { state: 'checking' }
  | { state: 'ok'; service: string }
  | { state: 'error'; message: string }

function App() {
  const [backend, setBackend] = useState<BackendStatus>({ state: 'checking' })

  useEffect(() => {
    fetch('/api/health')
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const body: { status: string; service: string } = await response.json()
        setBackend({ state: 'ok', service: body.service })
      })
      .catch((error: unknown) => {
        setBackend({
          state: 'error',
          message: error instanceof Error ? error.message : String(error),
        })
      })
  }, [])

  return (
    <main className="app">
      <h1>PULSE</h1>
      <p className="tagline">Discover the story behind the score.</p>

      <p className={`status status-${backend.state}`}>
        {backend.state === 'checking' && 'Checking backend…'}
        {backend.state === 'ok' && `Backend connected (${backend.service})`}
        {backend.state === 'error' && `Backend unreachable: ${backend.message}`}
      </p>
    </main>
  )
}

export default App

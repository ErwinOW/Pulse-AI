import { useEffect, useState } from 'react'
import './App.css'
import { api } from './api/client'
import type { Audience, Language, MatchSummary } from './api/types'
import { MatchView } from './MatchView'

const DEFAULT_MATCH = 'demo-high-press'
const SLOW_START_MS = 3000 // after this, explain that a free server may be waking up

type Loading =
  | { state: 'loading'; slow: boolean }
  | { state: 'ready'; matches: MatchSummary[] }
  | { state: 'error'; message: string }

function App() {
  const [loading, setLoading] = useState<Loading>({ state: 'loading', slow: false })
  const [matchId, setMatchId] = useState(DEFAULT_MATCH)
  const [audience, setAudience] = useState<Audience>('casual')
  const [language, setLanguage] = useState<Language>('en')

  useEffect(() => {
    const controller = new AbortController()
    const slow = window.setTimeout(() => setLoading({ state: 'loading', slow: true }), SLOW_START_MS)
    api
      .matches(controller.signal)
      .then((matches) => setLoading({ state: 'ready', matches }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) {
          setLoading({ state: 'error', message: e instanceof Error ? e.message : String(e) })
        }
      })
      .finally(() => window.clearTimeout(slow))
    return () => {
      controller.abort()
      window.clearTimeout(slow)
    }
  }, [])

  if (loading.state === 'loading') {
    return (
      <main className="centered">
        <p className="brand">PULSE</p>
        <p className="muted">
          {loading.slow
            ? 'Waking up the server. On the free plan this can take up to a minute…'
            : 'Loading…'}
        </p>
      </main>
    )
  }
  if (loading.state === 'error') {
    return (
      <main className="centered">
        <p className="brand">PULSE</p>
        <p className="error">The server didn't respond ({loading.message}). Reload to try again.</p>
      </main>
    )
  }

  const match = loading.matches.find((m) => m.match_id === matchId) ?? loading.matches[0]
  return (
    <MatchView
      key={match.match_id}
      match={match}
      matches={loading.matches}
      onMatchChange={setMatchId}
      audience={audience}
      onAudienceChange={setAudience}
      language={language}
      onLanguageChange={setLanguage}
    />
  )
}

export default App

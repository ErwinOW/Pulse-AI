import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { AskResponse, Audience, Language } from '../api/types'
import { hasKey, type T } from '../i18n'

type Props = {
  matchId: string
  endT: number // full-time clock; the API refuses earlier times
  audience: Audience
  language: Language
  t: T
}

type Turn = { question: string; response?: AskResponse; error?: string }

const MAX_QUESTION = 200

/** Post-match Q&A with the Analyst agent; shown once the replay reaches the final whistle. */
export function AskAnalyst({ matchId, endT, audience, language, t }: Props) {
  const [suggested, setSuggested] = useState<Record<string, string[]>>({})
  const [turns, setTurns] = useState<Turn[]>([]) // newest first
  const [draft, setDraft] = useState('')
  const busy = turns.length > 0 && !turns[0].response && !turns[0].error

  useEffect(() => {
    if (suggested[language]) return
    const controller = new AbortController()
    api
      .suggestedQuestions(language, controller.signal)
      .then((questions) => setSuggested((known) => ({ ...known, [language]: questions })))
      .catch(() => undefined) // the free-text box still works
    return () => controller.abort()
  }, [language, suggested])

  function ask(question: string) {
    const q = question.trim()
    if (!q || busy) return
    setTurns((known) => [{ question: q }, ...known])
    setDraft('')
    const settle = (update: Partial<Turn>) =>
      setTurns((known) => known.map((turn, i) => (i === 0 ? { ...turn, ...update } : turn)))
    api
      .ask(matchId, q, endT, audience, language)
      .then((response) => settle({ response }))
      .catch((e: unknown) => settle({ error: e instanceof Error ? e.message : String(e) }))
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    ask(draft)
  }

  return (
    <section className="card ask">
      <div className="insight-meta">
        <span className="badge badge-accent">{t('askTitle')}</span>
        <span className="muted">{t('askIntro')}</span>
      </div>
      <div className="ask-suggested">
        {(suggested[language] ?? []).map((question) => (
          <button key={question} type="button" disabled={busy} onClick={() => ask(question)}>
            {question}
          </button>
        ))}
      </div>
      <form className="ask-form" onSubmit={submit}>
        <input
          value={draft}
          maxLength={MAX_QUESTION}
          placeholder={t('askPlaceholder')}
          aria-label={t('askPlaceholder')}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          {t('askButton')}
        </button>
      </form>
      {turns.map((turn, i) => (
        <AnswerView key={turns.length - i} turn={turn} t={t} />
      ))}
    </section>
  )
}

function AnswerView({ turn, t }: { turn: Turn; t: T }) {
  const { response, error } = turn
  const answer = response?.answer
  return (
    <div className="ask-turn">
      <p className="ask-question">{turn.question}</p>
      {!response && !error && <p className="muted">{t('askThinking')}</p>}
      {error && <p className="error">{t('askError', { detail: error })}</p>}
      {answer && (
        <>
          <p>{answer.answer}</p>
          {answer.data_found.length > 0 && (
            <ul className="ask-data">
              {answer.data_found.map((fact) => (
                <li key={fact.label}>
                  {fact.label}: {fact.value}
                </li>
              ))}
            </ul>
          )}
          <div className="insight-actions">
            <SourceBadge response={response} t={t} />
            {answer.looked_at.length > 0 && (
              <span className="muted ask-looked">{t('askLookedAt', { tools: answer.looked_at.map((c) => toolLabel(c, t)).join(', ') })}</span>
            )}
            {!response.cached && answer.source !== 'declined' && (
              <span className="muted ask-looked">{t('askCallsLeft', { n: response.model_calls_left_today })}</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function SourceBadge({ response, t }: { response: AskResponse; t: T }) {
  const source = response.answer.source
  if (source === 'declined') return <span className="badge badge-muted">{t('askDeclined')}</span>
  if (source === 'fallback') return <span className="badge badge-muted">{t('askFallback')}</span>
  return response.cached ? (
    <span className="badge badge-success" title={t('askReviewedTitle')}>
      {t('askReviewed')}
    </span>
  ) : (
    <span className="badge badge-success" title={t('askLiveTitle')}>
      {t('askLive')}
    </span>
  )
}

/** "team_stats 45'-90'" -> "team stats 45'-90'" in the UI language. */
function toolLabel(call: string, t: T) {
  const [name, ...range] = call.split(' ')
  const key = `tool.${name}`
  return [hasKey(key) ? t(key) : name, ...range].join(' ')
}

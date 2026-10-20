import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Audience, Language, ReportResponse } from '../api/types'
import { hasKey, type T } from '../i18n'

type Props = {
  matchId: string
  endT: number // full-time clock; the API refuses earlier times
  audience: Audience
  language: Language
  t: T
}

/** Post-match commentary, shown once the replay reaches the final whistle. */
export function FullTimeReport({ matchId, endT, audience, language, t }: Props) {
  const [responses, setResponses] = useState<Record<string, ReportResponse>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const key = `${matchId}|${audience}|${language}`
  const data = responses[key]

  useEffect(() => {
    if (responses[key] || errors[key]) return
    const controller = new AbortController()
    api
      .report(matchId, endT, audience, language, controller.signal)
      .then((r) => setResponses((known) => ({ ...known, [key]: r })))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setErrors((known) => ({ ...known, [key]: e instanceof Error ? e.message : String(e) }))
      })
    return () => controller.abort()
  }, [matchId, endT, audience, language, key, responses, errors])

  const reason = data?.report.fallback_reason
  const reasonKey = `reason.${reason}`

  return (
    <section className="card report">
      <div className="insight-meta">
        <span className="badge badge-accent">{t('fullTimeReport')}</span>
      </div>
      {errors[key] && <p className="error">{t('insightError', { detail: errors[key] })}</p>}
      {!data && !errors[key] && <p className="muted">{t('loadingInsight')}</p>}
      {data && (
        <>
          <h3 className="insight-headline">{data.report.report.headline}</h3>
          <ol className="report-moments">
            {data.report.report.moments.map((moment) => (
              <li key={moment}>{moment}</li>
            ))}
          </ol>
          <p className="insight-why">{data.report.report.closing}</p>
          <div className="insight-actions">
            {data.report.source === 'ai' ? (
              <span className="badge badge-success" title={`${data.report.model}, ${data.report.prompt_version}`}>
                {t('aiWritten')}
              </span>
            ) : (
              <span className="badge badge-muted" title={t('templateTitle')}>
                {t('templateText')} · {reason && hasKey(reasonKey) ? t(reasonKey) : t('reason.other')}
              </span>
            )}
          </div>
        </>
      )}
    </section>
  )
}

import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Alert, Audience, InsightResponse, Language, MetricFact } from '../api/types'
import { clockLabel, describeEvent, minuteOf } from '../format'
import { hasKey, metricKey, type T } from '../i18n'

type Props = {
  matchId: string
  alerts: Alert[] // raised by the current match time
  audience: Audience
  language: Language
  teamNames: Record<string, string>
  t: T
}

function fallbackReason(reason: string | null, t: T): string {
  if (!reason) return t('templateText')
  const key = `reason.${reason}`
  return hasKey(key) ? t(key) : t('reason.other')
}

export function InsightCard({ matchId, alerts, audience, language, teamNames, t }: Props) {
  const [chosenId, setChosenId] = useState<string | null>(null)
  const [responses, setResponses] = useState<Record<string, InsightResponse>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [regenerating, setRegenerating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [evidenceChoice, setEvidenceChoice] = useState<boolean | null>(null)
  const showEvidence = evidenceChoice ?? audience === 'analyst' // analysts see the numbers first

  const alert = alerts.find((a) => a.alert_id === chosenId) ?? alerts.at(-1) ?? null
  const key = alert ? `${alert.alert_id}|${audience}|${language}` : ''
  const alertId = alert?.alert_id
  const data = responses[key]
  const error = errors[key]

  useEffect(() => {
    if (!alertId || responses[key] || errors[key]) return
    const controller = new AbortController()
    api
      .insight(matchId, alertId, audience, language, controller.signal)
      .then((response) => setResponses((known) => ({ ...known, [key]: response })))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) {
          setErrors((known) => ({ ...known, [key]: e instanceof Error ? e.message : String(e) }))
        }
      })
    return () => controller.abort()
  }, [matchId, alertId, audience, language, key, responses, errors])

  if (!alert) {
    return (
      <section className="card">
        <h2>{t('insight')}</h2>
        <p className="muted">{t('noAlert')}</p>
      </section>
    )
  }

  async function regenerate() {
    if (!alert) return
    setRegenerating(true)
    setNotice(null)
    try {
      const response = await api.regenerate(matchId, alert.alert_id, audience, language)
      setResponses((known) => ({ ...known, [key]: response }))
      if (response.insight.source !== 'ai') setNotice(t('showingTemplate', { reason: fallbackReason(response.insight.fallback_reason, t) }))
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setRegenerating(false)
    }
  }

  const number = new Intl.NumberFormat(language === 'id' ? 'id-ID' : 'en-GB', { maximumFractionDigits: 1 })
  const totalSignals = alert.detection_signals.length || alert.signals.length

  return (
    <section className="card insight">
      {alerts.length > 1 && (
        <div className="segmented alert-picker" role="group" aria-label={t('chooseAlert')}>
          {alerts.map((a) => (
            <button key={a.alert_id} aria-pressed={a.alert_id === alert.alert_id} onClick={() => setChosenId(a.alert_id)}>
              {teamNames[a.team_id] ?? a.team_id} {minuteOf(a.first_detected_s)}'
            </button>
          ))}
        </div>
      )}
      <div className="insight-meta">
        <span className="badge badge-accent">{t('alertAt', { minute: `${minuteOf(alert.first_detected_s)}'` })}</span>
        <span className="muted">
          {data
            ? `${data.facts.confidence === 'strong' ? t('strong') : t('moderate')} · ${t('signals', { met: data.facts.signals_met.length, total: totalSignals })}`
            : ''}
        </span>
        <span className="muted">
          {alert.active ? t('stillActive') : t('lastConfirmed', { minute: `${minuteOf(alert.last_confirmed_s)}'` })}
        </span>
      </div>

      {error && <p className="error">{t('insightError', { detail: error })}</p>}
      {!data && !error && <p className="muted">{t('loadingInsight')}</p>}
      {data && (
        <>
          <h3 className="insight-headline">{data.insight.narrative.headline}</h3>
          <p>{data.insight.narrative.summary}</p>
          <p className="insight-why">{data.insight.narrative.interpretation}</p>
          {data.facts.sample_note && <p className="badge badge-warning insight-note">{data.facts.sample_note}</p>}

          <div className="insight-actions">
            {data.insight.source === 'ai' ? (
              <span
                className="badge badge-success"
                title={`${data.insight.model}, prompt ${data.insight.prompt_version}, ${data.insight.attempts} attempt(s), ${data.cached ? 'saved' : 'new'} ${data.insight.generated_at}`}
              >
                {t('aiWritten')}
              </span>
            ) : (
              <span className="badge badge-muted" title={t('templateTitle')}>
                {t('templateText')} · {fallbackReason(data.insight.fallback_reason, t)}
              </span>
            )}
            <button onClick={() => setEvidenceChoice(!showEvidence)} aria-expanded={showEvidence}>
              {showEvidence ? t('hideEvidence') : t('showEvidence')}
            </button>
            <button
              onClick={regenerate}
              disabled={regenerating}
              title={t('regenerateTitle', { n: data.regenerations_left_today })}
            >
              {regenerating ? t('writing') : t('regenerate')}
            </button>
          </div>
          {notice && <p className="muted insight-notice">{notice}</p>}

          {showEvidence && <Evidence data={data} number={number} teamNames={teamNames} t={t} />}
        </>
      )}
    </section>
  )
}

function Evidence({
  data,
  number,
  teamNames,
  t,
}: {
  data: InsightResponse
  number: Intl.NumberFormat
  teamNames: Record<string, string>
  t: T
}) {
  const facts = new Map(data.facts.facts.map((f) => [f.fact_id, f]))
  const signalIds = [...new Set(data.facts.facts.map((f) => f.fact_id.split('.')[0]))]
  const cited = new Set(data.insight.narrative.event_ids)
  const citedEvents = (data.evidence_events ?? []).filter((e) => cited.has(e.event_id))
  const value = (f: MetricFact | undefined) => {
    if (!f || f.value === null) return '–'
    if (f.unit === 'percent') return `${number.format(f.value)}%`
    if (f.unit === 'per_min') return `${number.format(f.value)}${t('perMin')}`
    return number.format(f.value)
  }
  const span = (f: MetricFact | undefined) => (f ? `${minuteOf(f.window_start_s)}'–${minuteOf(f.window_end_s) - 1}'` : '')
  const label = (f: MetricFact | undefined) => {
    if (!f) return ''
    const key = metricKey(f.metric_id)
    return hasKey(key) ? t(key, { team: teamNames[f.team_id] ?? f.team_id }) : f.label.split(' (')[0]
  }
  const first = facts.get(`${signalIds[0]}.baseline`)
  const firstRecent = facts.get(`${signalIds[0]}.recent`)

  return (
    <div className="evidence">
      <table className="evidence-table">
        <thead>
          <tr>
            <th scope="col">{t('signal')}</th>
            <th scope="col">{t('before', { span: span(first) })}</th>
            <th scope="col">{t('now', { span: span(firstRecent) })}</th>
          </tr>
        </thead>
        <tbody>
          {signalIds.map((id) => {
            const before = facts.get(`${id}.baseline`)
            const now = facts.get(`${id}.recent`)
            return (
              <tr key={id}>
                <td>{label(now)}</td>
                <td>
                  {value(before)} <span className="muted">({value(facts.get(`${id}.baseline_count`))})</span>
                </td>
                <td>
                  {value(now)} <span className="muted">({value(facts.get(`${id}.recent_count`))})</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="muted evidence-caption">{t('countsNote')}</p>

      {citedEvents.length > 0 && <h4>{t('citedEvents')}</h4>}
      <ol className="feed">
        {citedEvents.map((e) => (
            <li key={e.event_id}>
              <span className="feed-time">{clockLabel(e.timestamp_seconds)}</span>
              <span className="feed-team">{e.team_id ? teamNames[e.team_id] ?? e.team_id : ''}</span>
              <span className="feed-text">{describeEvent(e, t)}</span>
              {e.under_pressure && <span className="tag tag-press">{t('underPressure')}</span>}
            </li>
          ))}
      </ol>
      <p className="muted evidence-caption">
        {t('backedBy', { n: data.facts.evidence_event_ids.length })}
      </p>
    </div>
  )
}

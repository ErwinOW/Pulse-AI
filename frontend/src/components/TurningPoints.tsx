import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Alert, MatchState, TurningPoint } from '../api/types'
import { minuteOf } from '../format'
import { hasKey, type T } from '../i18n'

type Props = {
  matchId: string
  goals: MatchState['goals'] // goals before the current match time
  alerts: Alert[]
  homeId: string
  awayId: string
  teamNames: Record<string, string>
  t: T
}

/** One line per goal: how the scoring move started, from the data (no AI). */
export function TurningPoints({ matchId, goals, alerts, homeId, awayId, teamNames, t }: Props) {
  const [byKey, setByKey] = useState<Record<string, TurningPoint[]>>({})
  const lastGoalT = goals.at(-1)?.timestamp_seconds
  const key = lastGoalT === undefined ? '' : `${matchId}|${lastGoalT}`
  const points = byKey[key] ?? []

  useEffect(() => {
    if (lastGoalT === undefined || byKey[key]) return
    const controller = new AbortController()
    // Ask for turning points just after the latest goal: the API only returns goals before t.
    api
      .turningPoints(matchId, lastGoalT + 0.5, controller.signal)
      .then((result) => setByKey((known) => ({ ...known, [key]: result })))
      .catch(() => undefined) // the panel stays empty; the rest of the page still works
    return () => controller.abort()
  }, [matchId, lastGoalT, key, byKey])

  const name = (teamId: string) => teamNames[teamId] ?? teamId
  const alertTeam = (alertId: string) =>
    alerts.find((a) => a.alert_id === alertId)?.team_id ?? alertId.split('-')[1] ?? ''

  return (
    <section className="card">
      <h2>{t('turningPoints')}</h2>
      {goals.length === 0 || points.length === 0 ? (
        <p className="muted">{t('noGoals')}</p>
      ) : (
        <ol className="turning-points">
          {points.map((p) => {
            const passes = p.possession_passes === 1 ? t('onePass') : t('passes', { n: p.possession_passes })
            const seconds = Math.round(p.possession_duration_s)
            const zoneKey = `zone.${p.turnover?.zone}`
            return (
              <li key={p.turning_point_id}>
                <p className="tp-title">
                  {t('goalLine', {
                    minute: `${minuteOf(p.timestamp_seconds)}'`,
                    team: name(p.team_id),
                    score: `${p.score_after[homeId] ?? 0}–${p.score_after[awayId] ?? 0}`,
                  })}
                </p>
                <p>
                  {p.turnover
                    ? t('fromTurnover', {
                        team: name(p.team_id),
                        opponent: name(p.turnover.lost_by),
                        pressure: p.turnover.under_pressure ? t('underPressureWord') : '',
                        zone: hasKey(zoneKey) ? t(zoneKey) : '',
                        seconds,
                        passes,
                      })
                    : t('notRecorded', { passes, seconds })}
                </p>
                {p.related_alert_ids.map((alertId) => (
                  <p key={alertId} className="muted tp-alert">
                    {t('duringAlert', { team: name(alertTeam(alertId)) })}
                  </p>
                ))}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

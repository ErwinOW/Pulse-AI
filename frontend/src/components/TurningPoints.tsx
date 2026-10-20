import type { Alert, TurningPoint } from '../api/types'
import { minuteOf } from '../format'
import { hasKey, type T } from '../i18n'

type Props = {
  points: TurningPoint[] // goals before the current match time
  selectedId: string | null // goal drawn on the pitch
  onSelect: (turningPointId: string) => void
  alerts: Alert[]
  homeId: string
  awayId: string
  teamNames: Record<string, string>
  t: T
}

/** One line per goal: how the scoring move started, from the data (no AI). */
export function TurningPoints({ points, selectedId, onSelect, alerts, homeId, awayId, teamNames, t }: Props) {
  const name = (teamId: string) => teamNames[teamId] ?? teamId
  const alertTeam = (alertId: string) =>
    alerts.find((a) => a.alert_id === alertId)?.team_id ?? alertId.split('-')[1] ?? ''

  return (
    <section className="card">
      <h2>{t('turningPoints')}</h2>
      {points.length === 0 ? (
        <p className="muted">{t('noGoals')}</p>
      ) : (
        <ol className="turning-points">
          {points.map((p) => {
            const passes = p.possession_passes === 1 ? t('onePass') : t('passes', { n: p.possession_passes })
            const seconds = Math.round(p.possession_duration_s)
            const zoneKey = `zone.${p.turnover?.zone}`
            return (
              <li key={p.turning_point_id} className={p.turning_point_id === selectedId ? 'tp-selected' : ''}>
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
                <button className="tp-pitch" onClick={() => onSelect(p.turning_point_id)} aria-pressed={p.turning_point_id === selectedId}>
                  {t('showOnPitch')}
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

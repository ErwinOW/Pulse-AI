import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Alert, MatchEvent, TeamInfo, TurningPoint } from '../api/types'
import { clockLabel, describeEvent, minuteOf } from '../format'
import type { T } from '../i18n'

// Pitch drawn in metres (105 x 68). Event coordinates are 0-100 in the acting team's
// direction of play; we flip the other team's events so one team always attacks right.
const L = 105
const W = 68

type Props = {
  matchId: string
  points: TurningPoint[]
  selectedId: string | null
  alerts: Alert[]
  home: TeamInfo
  away: TeamInfo
  t: T
}

type Mode = 'goal' | 'press'

export function PitchView({ matchId, points, selectedId, alerts, home, away, t }: Props) {
  const [modeChoice, setModeChoice] = useState<Mode | null>(null)
  const [evidence, setEvidence] = useState<Record<string, MatchEvent[]>>({})
  const alert = alerts.at(-1) ?? null
  const alertId = alert?.alert_id
  const goal = points.find((p) => p.turning_point_id === selectedId) ?? points.at(-1) ?? null
  const mode: Mode = modeChoice ?? (goal ? 'goal' : 'press')

  useEffect(() => {
    if (!alertId || evidence[alertId]) return
    const controller = new AbortController()
    // Evidence does not depend on audience or language; any version carries it.
    api
      .insight(matchId, alertId, 'analyst', 'en', controller.signal)
      .then((r) => setEvidence((known) => ({ ...known, [alertId]: r.evidence_events })))
      .catch(() => undefined)
    return () => controller.abort()
  }, [matchId, alertId, evidence])

  const color = (teamId?: string) => (teamId === home.team_id ? 'var(--series-home)' : 'var(--series-away)')
  const marker = (teamId?: string) => (teamId === home.team_id ? 'url(#arrow-home)' : 'url(#arrow-away)')
  const name = (teamId?: string) => (teamId === home.team_id ? home.short_name : away.short_name)

  const attacking = mode === 'goal' ? goal?.team_id : alert?.team_id
  /** 0-100 event coordinates -> pitch metres, with `attacking` playing left to right. */
  const at = (e: MatchEvent, x?: number, y?: number): [number, number] => {
    const flip = e.team_id !== attacking
    const px = flip ? 100 - (x ?? 0) : (x ?? 0)
    const py = flip ? 100 - (y ?? 0) : (y ?? 0)
    return [(px / 100) * L, W - (py / 100) * W] // y = 0 is the attacker's right touchline
  }

  const hasGoal = goal !== null
  const hasPress = alert !== null && (evidence[alert.alert_id]?.length ?? 0) > 0

  return (
    <section className="card">
      <div className="card-header">
        <h2>{t('pitch')}</h2>
        <div className="segmented" role="group" aria-label={t('pitch')}>
          <button aria-pressed={mode === 'goal'} onClick={() => setModeChoice('goal')} disabled={!hasGoal}>
            {t('pitchGoal')}
          </button>
          <button aria-pressed={mode === 'press'} onClick={() => setModeChoice('press')} disabled={!alert}>
            {t('pitchPress')}
          </button>
        </div>
      </div>

      {(mode === 'goal' && !hasGoal) || (mode === 'press' && !hasPress) ? (
        <p className="muted">{mode === 'goal' ? t('pitchNoGoal') : t('pitchNoPress')}</p>
      ) : (
        <>
          <p className="muted pitch-caption">
            {mode === 'goal' && goal
              ? t('pitchGoalCaption', { team: name(goal.team_id), minute: `${minuteOf(goal.timestamp_seconds)}'` })
              : alert && t('pitchPressCaption', { team: name(alert.team_id), minute: `${minuteOf(alert.first_detected_s)}'` })}
          </p>
          <svg className="pitch" viewBox={`-3 -3 ${L + 6} ${W + 10}`} role="img" aria-label={t('pitch')}>
            <defs>
              {(['home', 'away'] as const).map((side) => (
                <marker
                  key={side}
                  id={`arrow-${side}`}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto-start-reverse"
                >
                  <path d="M0,0 L10,5 L0,10 z" fill={`var(--series-${side})`} />
                </marker>
              ))}
            </defs>
            <PitchLines />
            {mode === 'goal' && goal && (
              <GoalChain events={goal.chain_events ?? []} at={at} color={color} marker={marker} />
            )}
            {mode === 'press' && alert && (
              <PressMap events={evidence[alert.alert_id] ?? []} pressingTeam={alert.team_id} at={at} color={color} />
            )}
            <text x={L / 2} y={W + 6} textAnchor="middle" className="pitch-direction">
              {t('attackingRight', { team: name(attacking) })}
            </text>
          </svg>

          {mode === 'goal' && goal ? (
            <ol className="pitch-steps">
              {(goal.chain_events ?? []).map((e, i) => (
                <li key={e.event_id}>
                  <span className="step-number" style={{ background: color(e.team_id) }}>
                    {i + 1}
                  </span>
                  <span className="feed-time">{clockLabel(e.timestamp_seconds)}</span>
                  <span className="feed-team">{name(e.team_id)}</span>
                  <span>{describeEvent(e, t)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="legend pitch-legend">
              <span>
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <circle cx="6" cy="6" r="4" fill="none" stroke={color(alert?.team_id)} strokeWidth="2" />
                </svg>
                {t('legendPressure', { team: name(alert?.team_id) })}
              </span>
              <span>
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <circle cx="6" cy="6" r="4" fill={color(alert?.team_id)} />
                </svg>
                {t('legendWon', { team: name(alert?.team_id) })}
              </span>
              <span>
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <path d="M2,2 L10,10 M10,2 L2,10" stroke={color(alert?.opponent_id)} strokeWidth="2" />
                </svg>
                {t('legendLost', { team: name(alert?.opponent_id) })}
              </span>
            </p>
          )}
        </>
      )}
    </section>
  )
}

function PitchLines() {
  const box = { d: 16.5, w: 40.3 }
  const six = { d: 5.5, w: 18.3 }
  return (
    <g className="pitch-lines">
      <rect x={0} y={0} width={L} height={W} />
      <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
      <circle cx={L / 2} cy={W / 2} r={9.15} />
      {[0, L].map((x) => {
        const dir = x === 0 ? 1 : -1
        return (
          <g key={x}>
            <rect x={x === 0 ? 0 : L - box.d} y={(W - box.w) / 2} width={box.d} height={box.w} />
            <rect x={x === 0 ? 0 : L - six.d} y={(W - six.w) / 2} width={six.d} height={six.w} />
            <rect x={x === 0 ? -2 : L} y={W / 2 - 3.66} width={2} height={7.32} />
            <circle cx={x + dir * 11} cy={W / 2} r={0.4} className="pitch-spot" />
          </g>
        )
      })}
    </g>
  )
}

type Draw = {
  at: (e: MatchEvent, x?: number, y?: number) => [number, number]
  color: (teamId?: string) => string
}

function GoalChain({ events, at, color, marker }: Draw & { events: MatchEvent[]; marker: (teamId?: string) => string }) {
  // Several steps often start at the same spot (press, lost pass, recovery): shift labels
  // sideways until they no longer overlap.
  const placed: [number, number][] = []
  const labelAt = (x: number, y: number): [number, number] => {
    let lx = x
    while (placed.some(([px, py]) => Math.abs(px - lx) < 3.8 && Math.abs(py - y) < 3.8)) lx += 4
    placed.push([lx, y])
    return [lx, y]
  }
  return (
    <g>
      {events.map((e, i) => {
        const [x1, y1] = at(e, e.start_x, e.start_y)
        const [lx, ly] = labelAt(x1, y1 - 3)
        const c = color(e.team_id)
        let mark: ReactNode
        if ((e.event_type === 'pass' || e.event_type === 'carry') && e.end_x !== undefined) {
          const [x2, y2] = at(e, e.end_x, e.end_y)
          const lost = e.outcome && e.outcome !== 'complete'
          mark = (
            <>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={c}
                strokeWidth={0.7}
                strokeDasharray={e.event_type === 'carry' ? '1.5 1' : undefined}
                markerEnd={lost ? undefined : marker(e.team_id)}
              />
              {lost && <Cross x={x2} y={y2} color={c} />}
            </>
          )
        } else if (e.event_type === 'shot') {
          mark = <line x1={x1} y1={y1} x2={L} y2={W / 2} stroke={c} strokeWidth={1.1} markerEnd={marker(e.team_id)} />
        } else if (e.event_type === 'pressure') {
          mark = <circle cx={x1} cy={y1} r={1.6} fill="none" stroke={c} strokeWidth={0.6} />
        } else {
          mark = <circle cx={x1} cy={y1} r={1.4} fill={c} />
        }
        return (
          <g key={e.event_id}>
            {mark}
            <circle cx={lx} cy={ly} r={1.8} fill={c} />
            <text x={lx} y={ly + 0.7} textAnchor="middle" className="pitch-step">
              {i + 1}
            </text>
          </g>
        )
      })}
    </g>
  )
}

function PressMap({ events, pressingTeam, at, color }: Draw & { events: MatchEvent[]; pressingTeam: string }) {
  return (
    <g>
      {events.map((e) => {
        const [x, y] = at(e, e.start_x, e.start_y)
        const c = color(e.team_id)
        if (e.team_id !== pressingTeam) return <Cross key={e.event_id} x={x} y={y} color={c} />
        if (e.event_type === 'pressure') {
          return <circle key={e.event_id} cx={x} cy={y} r={1.5} fill="none" stroke={c} strokeWidth={0.6} />
        }
        return <circle key={e.event_id} cx={x} cy={y} r={1.4} fill={c} />
      })}
    </g>
  )
}

function Cross({ x, y, color }: { x: number; y: number; color: string }) {
  const s = 1.4
  return (
    <path d={`M${x - s},${y - s} L${x + s},${y + s} M${x + s},${y - s} L${x - s},${y + s}`} stroke={color} strokeWidth={0.7} />
  )
}

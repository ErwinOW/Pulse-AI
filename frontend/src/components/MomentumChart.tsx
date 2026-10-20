import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Alert, Audience, MatchState, TeamInfo } from '../api/types'
import { minuteOf } from '../format'
import type { T } from '../i18n'

const FULL_MATCH_MIN = 90
const TICKS = [15, 30, 45, 60, 75, 90]
const MIN_SCALE = 5 // keeps small early swings from filling the whole height

type Props = {
  snapshot: MatchState | null
  home: TeamInfo
  away: TeamInfo
  audience: Audience
  t: T
}

type Point = { minute: number; diff: number | null }

/**
 * Who has the upper hand, minute by minute: home momentum minus away momentum
 * (weighted attacking actions in the last 5 minutes). Bars above the middle line
 * favour the home team, below favour the away team. Alert windows are shaded and
 * goals marked on the scoring team's side. The x axis always spans the full match.
 */
export function MomentumChart({ snapshot, home, away, audience, t }: Props) {
  const analyst = audience === 'analyst'
  const byMinute = new Map((snapshot?.momentum ?? []).map((p) => [Math.round(p.end_s / 60), p.diff]))
  const points: Point[] = Array.from({ length: FULL_MATCH_MIN }, (_, i) => ({
    minute: i + 1,
    diff: byMinute.get(i + 1) ?? null,
  }))
  const scale = Math.max(MIN_SCALE, ...[...byMinute.values()].map((d) => Math.ceil(Math.abs(d))))
  const alerts: Alert[] = snapshot?.alerts ?? []
  const goals = snapshot?.goals ?? []
  const isHome = (teamId: string) => teamId === home.team_id
  const short = (teamId: string) => (isHome(teamId) ? home.short_name : away.short_name)
  const clampMinute = (s: number) => Math.min(FULL_MATCH_MIN, Math.max(1, minuteOf(s)))

  return (
    <section className="card">
      <div className="card-header">
        <h2>{analyst ? t('momentumAnalyst') : t('whoIsOnTop')}</h2>
        <div className="legend" aria-hidden="true">
          <span>
            <i className="swatch swatch-bar" style={{ background: 'var(--series-home)' }} />
            {t('above', { team: home.short_name })}
          </span>
          <span>
            <i className="swatch swatch-bar" style={{ background: 'var(--series-away)' }} />
            {t('below', { team: away.short_name })}
          </span>
        </div>
      </div>
      <div
        className="chart"
        role="img"
        aria-label={`Momentum balance by minute: bars above the middle line favour ${home.name}, below favour ${away.name}. ${alerts.length} alert window(s) and ${goals.length} goal(s) marked.`}
      >
        {byMinute.size === 0 ? (
          <p className="muted chart-empty">{t('chartEmpty')}</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 16, right: 8, bottom: 0, left: analyst ? -8 : -28 }} barCategoryGap={1}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis
                dataKey="minute"
                ticks={TICKS}
                interval={0}
                tickFormatter={(m: number) => `${m}'`}
                stroke="var(--grid)"
                tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
              />
              <YAxis
                domain={[-scale, scale]}
                ticks={[-scale, 0, scale]}
                tickFormatter={(v: number) => (analyst ? String(Math.abs(v)) : '')}
                tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                stroke="var(--grid)"
                width={36}
              />
              {alerts.map((a) => (
                <ReferenceArea
                  key={a.alert_id}
                  x1={clampMinute(a.onset_s)}
                  x2={clampMinute(a.last_confirmed_s)}
                  fill="var(--text-muted)"
                  fillOpacity={0.12}
                  stroke="none"
                  label={{
                    value: t('pressAlert', { team: short(a.team_id) }),
                    position: 'insideTop', // goal labels sit at the bottom for away goals; keep clear
                    fill: 'var(--text-muted)',
                    fontSize: 11,
                  }}
                />
              ))}
              <ReferenceLine y={0} stroke="var(--text-muted)" />
              {goals.map((g) => (
                <ReferenceLine
                  key={g.event_id}
                  x={clampMinute(g.timestamp_seconds)}
                  stroke="var(--text-muted)"
                  strokeDasharray="3 3"
                  label={{
                    value: t('goalMarker', { team: short(g.team_id) }),
                    position: isHome(g.team_id) ? 'insideTopLeft' : 'insideBottomLeft',
                    fill: 'var(--text-muted)',
                    fontSize: 11,
                  }}
                />
              ))}
              <Tooltip
                cursor={{ fill: 'var(--grid)' }}
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as Point | undefined
                  if (!active || !point || point.diff === null) return null
                  const leader = point.diff > 0 ? home : point.diff < 0 ? away : null
                  return (
                    <div className="chart-tooltip">
                      <strong>{point.minute}'</strong>{' '}
                      {leader
                        ? t('onTopBy', { team: leader.short_name, value: Math.abs(point.diff).toFixed(1) })
                        : t('even')}
                    </div>
                  )
                }}
              />
              <Bar dataKey="diff" isAnimationActive={false}>
                {points.map((p) => (
                  <Cell
                    key={p.minute}
                    fill={p.diff !== null && p.diff < 0 ? 'var(--series-away)' : 'var(--series-home)'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        <span className="chart-side chart-side-top">{home.short_name} ↑</span>
        <span className="chart-side chart-side-bottom">{away.short_name} ↓</span>
      </div>
      <p className="chart-note muted">{t('chartNote')}</p>
    </section>
  )
}

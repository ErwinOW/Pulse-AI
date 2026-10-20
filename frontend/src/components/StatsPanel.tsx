import type { Language, MatchState, Metric, TeamInfo, TeamStats } from '../api/types'
import type { T } from '../i18n'

type Props = {
  snapshot: MatchState | null
  home: TeamInfo
  away: TeamInfo
  language: Language
  t: T
}

type Row = {
  label: Parameters<T>[0]
  pick: (s: TeamStats) => Metric
  unit: '%' | '/min' | ''
}

const ROWS: Row[] = [
  { label: 'stat.possession', pick: (s) => s.possession_share, unit: '%' },
  { label: 'stat.passCompletion', pick: (s) => s.pass_completion, unit: '%' },
  { label: 'stat.highPresses', pick: (s) => s.high_pressures_per_min, unit: '/min' },
  { label: 'stat.lostUnderPressure', pick: (s) => s.turnovers_under_pressure, unit: '' },
  { label: 'stat.shots', pick: (s) => s.shots, unit: '' },
  { label: 'stat.boxEntries', pick: (s) => s.box_entries, unit: '' },
]

/** Analyst view: each team's numbers in the last 5 minutes next to the whole match so far. */
export function StatsPanel({ snapshot, home, away, language, t }: Props) {
  if (!snapshot) return null
  const number = new Intl.NumberFormat(language === 'id' ? 'id-ID' : 'en-GB', { maximumFractionDigits: 1 })
  const cell = (window: MatchState['window'], teamId: string, row: Row) => {
    const stats = window.teams[teamId]
    const value = stats ? row.pick(stats).value : null
    if (value === null) return '–'
    const unit = row.unit === '/min' ? t('perMin') : row.unit
    return `${number.format(value)}${unit}`
  }

  return (
    <section className="card">
      <h2>{t('stat.title')}</h2>
      <table className="stats-table">
        <thead>
          <tr>
            <th scope="col" />
            <th scope="col" colSpan={2}>
              <i className="swatch swatch-bar" style={{ background: 'var(--series-home)' }} /> {home.short_name}
            </th>
            <th scope="col" colSpan={2}>
              <i className="swatch swatch-bar" style={{ background: 'var(--series-away)' }} /> {away.short_name}
            </th>
          </tr>
          <tr className="muted">
            <th scope="col" />
            <th scope="col">{t('stat.last5')}</th>
            <th scope="col">{t('stat.match')}</th>
            <th scope="col">{t('stat.last5')}</th>
            <th scope="col">{t('stat.match')}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label}>
              <th scope="row">{t(row.label)}</th>
              <td>{cell(snapshot.window, home.team_id, row)}</td>
              <td className="muted">{cell(snapshot.totals, home.team_id, row)}</td>
              <td>{cell(snapshot.window, away.team_id, row)}</td>
              <td className="muted">{cell(snapshot.totals, away.team_id, row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted evidence-caption">{t('stat.note')}</p>
    </section>
  )
}

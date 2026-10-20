import type { Audience, Language, MatchSummary } from './api/types'
import { EventFeed } from './components/EventFeed'
import { InsightCard } from './components/InsightCard'
import { MomentumChart } from './components/MomentumChart'
import { clockLabel } from './format'
import { useReplay } from './hooks/useReplay'

const SPEEDS = [1, 5, 10, 30, 60]

type Props = {
  match: MatchSummary
  matches: MatchSummary[]
  onMatchChange: (matchId: string) => void
  audience: Audience
  onAudienceChange: (audience: Audience) => void
  language: Language
  onLanguageChange: (language: Language) => void
}

export function MatchView(props: Props) {
  const { match } = props
  const replay = useReplay(match.match_id, match.duration_s)
  const home = match.home.team_id
  const away = match.away.team_id

  return (
    <div className="page">
      <header className="card scoreboard">
        <span className="brand">PULSE</span>
        {match.is_synthetic && <span className="badge badge-warning">Synthetic data</span>}
        <span className="spacer" />
        <span className="team">{match.home.name}</span>
        <span className="score">
          {replay.score[home] ?? 0} – {replay.score[away] ?? 0}
        </span>
        <span className="team">{match.away.name}</span>
        <span className="clock" title="Match clock">
          {clockLabel(replay.t)}
          {replay.ended ? ' · FT' : replay.period ? ` · ${replay.period === 1 ? '1st' : '2nd'} half` : ''}
        </span>
      </header>

      <section className="controls" aria-label="Replay controls">
        <button
          onClick={replay.playing ? replay.pause : replay.play}
          aria-label={replay.playing ? 'Pause' : 'Play'}
          disabled={replay.transport === 'connecting'}
        >
          {replay.playing ? 'Pause' : 'Play'}
        </button>
        <input
          type="range"
          className="timeline"
          min={0}
          max={Math.ceil(match.duration_s)}
          step={1}
          value={Math.min(replay.t, match.duration_s)}
          onChange={(e) => replay.seek(Number(e.target.value))}
          aria-label="Match time"
        />
        <label>
          Speed
          <select value={replay.speed} onChange={(e) => replay.setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
        <label>
          Audience
          <select value={props.audience} onChange={(e) => props.onAudienceChange(e.target.value as Audience)}>
            <option value="casual">Casual</option>
            <option value="analyst">Analyst</option>
          </select>
        </label>
        <label>
          Language
          <select value={props.language} onChange={(e) => props.onLanguageChange(e.target.value as Language)}>
            <option value="en">English</option>
            <option value="id">Bahasa Indonesia</option>
          </select>
        </label>
        {props.matches.length > 1 && (
          <label>
            Match
            <select value={match.match_id} onChange={(e) => props.onMatchChange(e.target.value)}>
              {props.matches.map((m) => (
                <option key={m.match_id} value={m.match_id}>
                  {m.match_id}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className={`transport transport-${replay.transport}`}>
          {replay.transport === 'websocket' && 'Live stream'}
          {replay.transport === 'polling' && 'Polling fallback'}
          {replay.transport === 'connecting' && 'Connecting…'}
        </span>
      </section>

      {replay.error && <p className="error">{replay.error}</p>}

      <div className="grid">
        <div className="column">
          <MomentumChart snapshot={replay.snapshot} home={match.home} away={match.away} />
          <EventFeed
            events={replay.events}
            tags={replay.tags}
            teamNames={{ [home]: match.home.short_name, [away]: match.away.short_name }}
          />
        </div>
        <div className="column">
          <InsightCard
            matchId={match.match_id}
            alerts={replay.snapshot?.alerts ?? []}
            audience={props.audience}
            language={props.language}
            teamNames={{ [home]: match.home.short_name, [away]: match.away.short_name }}
          />
          <section className="card">
            <h2>Turning points</h2>
            <p className="muted">Comes in step 4</p>
          </section>
        </div>
      </div>
    </div>
  )
}

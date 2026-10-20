import { useState } from 'react'
import type { Audience, Language, MatchSummary } from './api/types'
import { AskAnalyst } from './components/AskAnalyst'
import { EventFeed } from './components/EventFeed'
import { FullTimeReport } from './components/FullTimeReport'
import { InsightCard } from './components/InsightCard'
import { MomentumChart } from './components/MomentumChart'
import { PitchView } from './components/PitchView'
import { StatsPanel } from './components/StatsPanel'
import { TurningPoints } from './components/TurningPoints'
import { clockLabel } from './format'
import { useReplay } from './hooks/useReplay'
import { useTurningPoints } from './hooks/useTurningPoints'
import { translator } from './i18n'

const SPEEDS = [1, 5, 10, 30, 60]
const MATCH_LABELS: Record<string, Record<Language, string>> = {
  'demo-high-press': { en: 'Demo: high-press turning point', id: 'Demo: titik balik pressing tinggi' },
  balanced: { en: 'Balanced match', id: 'Pertandingan seimbang' },
}

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
  const { match, language } = props
  const t = translator(language)
  const replay = useReplay(match.match_id, match.duration_s)
  const home = match.home.team_id
  const away = match.away.team_id
  const teamNames = { [home]: match.home.short_name, [away]: match.away.short_name }
  const points = useTurningPoints(match.match_id, replay.snapshot?.goals ?? [])
  const [pitchGoalId, setPitchGoalId] = useState<string | null>(null)
  const half = replay.ended
    ? t('fullTime')
    : replay.period === 1
      ? t('firstHalf')
      : replay.period === 2
        ? t('secondHalf')
        : ''

  return (
    <div className="page">
      <header className="card scoreboard">
        <span className="brand">PULSE</span>
        {match.is_synthetic && (
          <span className="badge badge-warning" title={t('syntheticTitle')}>
            {t('synthetic')}
          </span>
        )}
        <span className="spacer" />
        <span className="team">{match.home.name}</span>
        <span className="score">
          {replay.score[home] ?? 0} – {replay.score[away] ?? 0}
        </span>
        <span className="team">{match.away.name}</span>
      </header>

      <section className="controls" aria-label={t('matchTime')}>
        <div className="timeline-row">
          <button
            className="play"
            onClick={replay.playing ? replay.pause : replay.play}
            disabled={replay.transport === 'connecting'}
          >
            {replay.playing ? t('pause') : t('play')}
          </button>
          <input
            type="range"
            className="timeline"
            min={0}
            max={Math.ceil(match.duration_s)}
            step={1}
            value={Math.min(replay.t, match.duration_s)}
            onChange={(e) => replay.seek(Number(e.target.value))}
            aria-label={t('matchTime')}
          />
          <span className="clock">
            {clockLabel(replay.t)}
            {half && ` · ${half}`}
          </span>
        </div>
        <div className="options-row">
          <label>
            {t('speed')}
            <select value={replay.speed} onChange={(e) => replay.setSpeed(Number(e.target.value))}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('audience')}
            <select value={props.audience} onChange={(e) => props.onAudienceChange(e.target.value as Audience)}>
              <option value="casual">{t('casual')}</option>
              <option value="analyst">{t('analyst')}</option>
            </select>
          </label>
          <label>
            {t('language')}
            <select value={language} onChange={(e) => props.onLanguageChange(e.target.value as Language)}>
              <option value="en">English</option>
              <option value="id">Bahasa Indonesia</option>
            </select>
          </label>
          {props.matches.length > 1 && (
            <label>
              {t('match')}
              <select value={match.match_id} onChange={(e) => props.onMatchChange(e.target.value)}>
                {props.matches.map((m) => (
                  <option key={m.match_id} value={m.match_id}>
                    {MATCH_LABELS[m.match_id]?.[language] ?? m.match_id}
                  </option>
                ))}
              </select>
            </label>
          )}
          <span className="spacer" />
          <span className={`transport transport-${replay.transport}`}>
            {replay.transport === 'websocket' && t('liveStream')}
            {replay.transport === 'polling' && t('polling')}
            {replay.transport === 'connecting' && t('connecting')}
          </span>
        </div>
      </section>

      {replay.error && <p className="error">{replay.error}</p>}

      <div className="grid">
        <div className="column">
          <MomentumChart snapshot={replay.snapshot} home={match.home} away={match.away} audience={props.audience} t={t} />
          <PitchView
            matchId={match.match_id}
            points={points}
            selectedId={pitchGoalId}
            alerts={replay.snapshot?.alerts ?? []}
            home={match.home}
            away={match.away}
            t={t}
          />
          <EventFeed events={replay.events} tags={replay.tags} teamNames={teamNames} audience={props.audience} t={t} />
        </div>
        <div className="column">
          {replay.ended && (
            <>
              <FullTimeReport
                matchId={match.match_id}
                endT={match.duration_s + 1}
                audience={props.audience}
                language={language}
                t={t}
              />
              <AskAnalyst
                key={match.match_id}
                matchId={match.match_id}
                endT={match.duration_s + 1}
                audience={props.audience}
                language={language}
                t={t}
              />
            </>
          )}
          <InsightCard
            matchId={match.match_id}
            alerts={replay.snapshot?.alerts ?? []}
            audience={props.audience}
            language={language}
            teamNames={teamNames}
            t={t}
          />
          {props.audience === 'analyst' && (
            <StatsPanel snapshot={replay.snapshot} home={match.home} away={match.away} language={language} t={t} />
          )}
          <TurningPoints
            points={points}
            selectedId={pitchGoalId}
            onSelect={setPitchGoalId}
            alerts={replay.snapshot?.alerts ?? []}
            homeId={home}
            awayId={away}
            teamNames={teamNames}
            t={t}
          />
        </div>
      </div>
    </div>
  )
}

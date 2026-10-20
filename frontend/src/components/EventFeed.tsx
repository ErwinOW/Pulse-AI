import { useState } from 'react'
import type { KeyTag, MatchEvent } from '../api/types'
import { clockLabel } from '../format'

const SHOWN = 15

const TAG_LABELS: Record<KeyTag, string> = {
  goal: 'Goal',
  shot: 'Shot',
  key_pass: 'Key pass',
  box_entry: 'Box entry',
  ball_won_high: 'Ball won high',
  lost_under_pressure: 'Lost under pressure',
  winning_press: 'Press',
  foul: 'Foul',
  substitution: 'Substitution',
  period: '',
}

// Colour groups: chance creation, pressing, result, other.
const TAG_KIND: Record<KeyTag, string> = {
  goal: 'goal',
  shot: 'chance',
  key_pass: 'chance',
  box_entry: 'chance',
  ball_won_high: 'press',
  lost_under_pressure: 'press',
  winning_press: 'press',
  foul: 'other',
  substitution: 'other',
  period: 'other',
}

const EVENT_LABELS: Record<string, string> = {
  pass: 'Pass',
  carry: 'Carry',
  shot: 'Shot',
  pressure: 'Pressure',
  tackle: 'Tackle',
  interception: 'Interception',
  ball_recovery: 'Ball recovery',
  foul: 'Foul',
  substitution: 'Substitution',
}

function periodLabel(e: MatchEvent): string {
  if (e.event_type === 'period_start') return e.period === 1 ? 'Kick-off' : 'Second half'
  return e.period === 1 ? 'Half-time' : 'Full-time'
}

function describe(e: MatchEvent): string {
  if (e.event_type === 'period_start' || e.event_type === 'period_end') return periodLabel(e)
  const base = EVENT_LABELS[e.event_type] ?? e.event_type
  if (e.event_type === 'shot' && e.outcome) return `${base} (${e.outcome.replace('_', ' ')})`
  if (e.event_type === 'pass' && e.outcome && e.outcome !== 'complete') return `${base} (${e.outcome})`
  return base
}

type Props = {
  events: MatchEvent[] // newest last
  tags: Record<string, KeyTag[]>
  teamNames: Record<string, string>
}

export function EventFeed({ events, tags, teamNames }: Props) {
  const [mode, setMode] = useState<'key' | 'all'>('key')
  const shown = (mode === 'key' ? events.filter((e) => tags[e.event_id]) : events).slice(-SHOWN).reverse()

  return (
    <section className="card">
      <div className="card-header">
        <h2>{mode === 'key' ? 'Key events' : 'All events'}</h2>
        <div className="segmented" role="group" aria-label="Event filter">
          <button aria-pressed={mode === 'key'} onClick={() => setMode('key')}>
            Key events
          </button>
          <button aria-pressed={mode === 'all'} onClick={() => setMode('all')}>
            All events
          </button>
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="muted">{mode === 'key' ? 'No key events yet' : 'No events yet'}</p>
      ) : (
        <ol className="feed">
          {shown.map((e) => (
            <li key={e.event_id}>
              <span className="feed-time">{clockLabel(e.timestamp_seconds)}</span>
              <span className="feed-team">{e.team_id ? teamNames[e.team_id] ?? e.team_id : ''}</span>
              <span className="feed-text">{describe(e)}</span>
              {(tags[e.event_id] ?? [])
                .filter((tag) => TAG_LABELS[tag])
                .map((tag) => (
                  <span key={tag} className={`tag tag-${TAG_KIND[tag]}`}>
                    {TAG_LABELS[tag]}
                  </span>
                ))}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

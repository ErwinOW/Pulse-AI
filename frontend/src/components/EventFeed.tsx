import { useState } from 'react'
import type { Audience, KeyTag, MatchEvent } from '../api/types'
import { clockLabel, describeEvent } from '../format'
import { hasKey, tagKey, type T } from '../i18n'

const SHOWN = 15

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

type Props = {
  events: MatchEvent[] // newest last
  tags: Record<string, KeyTag[]>
  teamNames: Record<string, string>
  audience: Audience
  t: T
}

/** Pitch third of an on-ball event, in the acting team's direction of play. */
function thirdKey(e: MatchEvent): string | null {
  if (e.start_x === undefined || e.event_type === 'pressure') return null
  return `third.${e.start_x < 100 / 3 ? 'defensive' : e.start_x < 200 / 3 ? 'middle' : 'final'}`
}

export function EventFeed({ events, tags, teamNames, audience, t }: Props) {
  const [mode, setMode] = useState<'key' | 'all'>('key')
  const shown = (mode === 'key' ? events.filter((e) => tags[e.event_id]) : events).slice(-SHOWN).reverse()

  return (
    <section className="card">
      <div className="card-header">
        <h2>{mode === 'key' ? t('keyEvents') : t('allEvents')}</h2>
        <div className="segmented" role="group" aria-label={t('keyEvents')}>
          <button aria-pressed={mode === 'key'} onClick={() => setMode('key')}>
            {t('keyEvents')}
          </button>
          <button aria-pressed={mode === 'all'} onClick={() => setMode('all')}>
            {t('allEvents')}
          </button>
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="muted">{mode === 'key' ? t('noKeyEvents') : t('noEvents')}</p>
      ) : (
        <ol className="feed">
          {shown.map((e) => (
            <li key={e.event_id}>
              <span className="feed-time">{clockLabel(e.timestamp_seconds)}</span>
              <span className="feed-team">{e.team_id ? teamNames[e.team_id] ?? e.team_id : ''}</span>
              <span className="feed-text">{describeEvent(e, t)}</span>
              {audience === 'analyst' && (() => {
                const key = thirdKey(e)
                return key && hasKey(key) ? <span className="feed-where">{t(key)}</span> : null
              })()}
              {(tags[e.event_id] ?? [])
                .filter((tag) => t(tagKey(tag)))
                .map((tag) => (
                  <span key={tag} className={`tag tag-${TAG_KIND[tag]}`}>
                    {t(tagKey(tag))}
                  </span>
                ))}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

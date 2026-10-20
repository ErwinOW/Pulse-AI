import type { MatchEvent } from './api/types'
import { eventKey, hasKey, outcomeKey, type T } from './i18n'

/** Match clock: 3813.7 -> "63:33" (continuous clock, 45:00 = start of the second half). */
export function clockLabel(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Match minute that contains time s (61:30 -> 62). */
export const minuteOf = (s: number) => Math.floor(s / 60) + 1

/** Short description of an event in the chosen UI language. */
export function describeEvent(e: MatchEvent, t: T): string {
  if (e.event_type === 'period_start') return e.period === 1 ? t('kickOff') : t('secondHalfStart')
  if (e.event_type === 'period_end') return e.period === 1 ? t('halfTime') : t('fullTimeEvent')
  const key = eventKey(e.event_type)
  const base = hasKey(key) ? t(key) : e.event_type
  const showOutcome = e.event_type === 'shot' || (e.event_type === 'pass' && e.outcome !== 'complete')
  if (showOutcome && e.outcome) {
    const outcome = outcomeKey(e.outcome)
    return `${base} (${hasKey(outcome) ? t(outcome) : e.outcome})`
  }
  return base
}

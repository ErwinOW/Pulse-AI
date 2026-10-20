import type { MatchEvent } from './api/types'

/** Match clock: 3813.7 -> "63:33" (continuous clock, 45:00 = start of the second half). */
export function clockLabel(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
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

export function describeEvent(e: MatchEvent): string {
  if (e.event_type === 'period_start' || e.event_type === 'period_end') return periodLabel(e)
  const base = EVENT_LABELS[e.event_type] ?? e.event_type
  if (e.event_type === 'shot' && e.outcome) return `${base} (${e.outcome.replace('_', ' ')})`
  if (e.event_type === 'pass' && e.outcome && e.outcome !== 'complete') return `${base} (${e.outcome})`
  return base
}

/** Match minute that contains time s (61:30 -> 62). */
export const minuteOf = (s: number) => Math.floor(s / 60) + 1

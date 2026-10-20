// Types mirroring the backend's Pydantic models (backend/app/**). Keep in sync by hand;
// only the fields the UI reads are listed where the backend sends more.

export type TeamInfo = { team_id: string; name: string; short_name: string }

export type MatchSummary = {
  match_id: string
  home: TeamInfo
  away: TeamInfo
  duration_s: number
  is_synthetic: boolean
}

// Events are a union on the backend; the UI treats them as one loose shape.
export type MatchEvent = {
  event_id: string
  event_type: string
  period: 1 | 2
  timestamp_seconds: number
  team_id?: string
  player_id?: string
  start_x?: number
  start_y?: number
  end_x?: number
  end_y?: number
  outcome?: string
  under_pressure?: boolean
  recipient_id?: string | null
}

// Key-event labels (backend/app/stats/key_events.py): what the "Key events" feed shows.
export type KeyTag =
  | 'goal'
  | 'shot'
  | 'key_pass'
  | 'box_entry'
  | 'ball_won_high'
  | 'lost_under_pressure'
  | 'winning_press'
  | 'foul'
  | 'substitution'
  | 'period'

export type Metric = { definition_id: string; value: number | null; sample_size: number }

export type TeamStats = {
  team_id: string
  possession_share: Metric
  pass_completion: Metric
  turnovers: Metric
  turnovers_under_pressure: Metric
  shots: Metric
  shots_on_target: Metric
  box_entries: Metric
  pressures_per_min: Metric
  high_pressures_per_min: Metric
  momentum: Metric
}

export type WindowStats = { start_s: number; end_s: number; teams: Record<string, TeamStats> }

export type MomentumPoint = { end_s: number; home: number; away: number; diff: number }

export type SignalCheck = {
  signal_id: string
  description: string
  team_id: string
  metric_id: string
  unit: string
  baseline_value: number | null
  recent_value: number | null
  baseline_sample_size: number
  recent_sample_size: number
  passed: boolean
}

export type Alert = {
  alert_id: string
  kind: 'pressing_increase'
  team_id: string
  opponent_id: string
  title: string
  onset_s: number
  first_detected_s: number
  last_confirmed_s: number
  active: boolean
  confidence: 'moderate' | 'strong'
  signals: SignalCheck[]
  evidence_event_ids: string[]
  sample_note: string | null
  detection_signals: SignalCheck[]
  detection_confidence: 'moderate' | 'strong' | null
}

export type MatchState = {
  match_id: string
  t: number
  minute: number
  period: number | null
  score: Record<string, number>
  recent_events: MatchEvent[]
  key_events: MatchEvent[] // last labelled events, newest last
  event_tags: Record<string, KeyTag[]>
  window: WindowStats
  totals: WindowStats
  momentum: MomentumPoint[]
  goals: { event_id: string; team_id: string; timestamp_seconds: number }[]
  alerts: Alert[]
}

// WebSocket replay messages (backend/app/api/replay.py).
export type ReplayControl = {
  type: 'control'
  t: number
  speed: number
  paused: boolean
  duration_s: number
}
export type ReplayTick = {
  type: 'tick'
  t: number
  minute: number
  period: number | null
  score: Record<string, number>
  events: MatchEvent[]
  new_alerts: Alert[]
  new_tags: Record<string, KeyTag[]> // may label events sent in earlier ticks
}
export type ReplayEnd = { type: 'end'; t: number; score: Record<string, number> }
export type ReplayError = { type: 'error'; detail: string }
export type ReplayMessage = ReplayControl | ReplayTick | ReplayEnd | ReplayError

export type Audience = 'casual' | 'analyst'
export type Language = 'en' | 'id'

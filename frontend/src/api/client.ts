// Thin fetch wrapper for the PULSE API. In development Vite proxies /api to FastAPI;
// in production VITE_API_URL can point at the backend when the frontend is hosted separately.
import type { Audience, InsightResponse, Language, MatchState, MatchSummary, TurningPoint } from './types'

const API_BASE: string = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function getJson<T>(path: string, signal?: AbortSignal, method = 'GET'): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal, method })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body: { detail?: unknown } = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // not JSON; keep the status text
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export const api = {
  matches: (signal?: AbortSignal) => getJson<MatchSummary[]>('/api/matches', signal),
  state: (matchId: string, t: number, signal?: AbortSignal) =>
    getJson<MatchState>(`/api/matches/${encodeURIComponent(matchId)}/state?t=${t}`, signal),
  turningPoints: (matchId: string, t: number, signal?: AbortSignal) =>
    getJson<TurningPoint[]>(`/api/matches/${encodeURIComponent(matchId)}/turning-points?t=${t}`, signal),
  insight: (matchId: string, alertId: string, audience: Audience, language: Language, signal?: AbortSignal) =>
    getJson<InsightResponse>(insightPath(matchId, alertId, audience, language), signal),
  regenerate: (matchId: string, alertId: string, audience: Audience, language: Language) =>
    getJson<InsightResponse>(insightPath(matchId, alertId, audience, language, '/regenerate'), undefined, 'POST'),
}

function insightPath(matchId: string, alertId: string, audience: Audience, language: Language, suffix = '') {
  const query = new URLSearchParams({ audience, language })
  return `/api/matches/${encodeURIComponent(matchId)}/insights/${encodeURIComponent(alertId)}${suffix}?${query}`
}

/** ws:// or wss:// URL for a backend path, matching the API's origin. */
export function wsUrl(path: string): string {
  const base = API_BASE || window.location.origin
  return base.replace(/^http/, 'ws') + path
}

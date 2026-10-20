// Match replay state: WebSocket stream first, polling /state as the fallback.
//
// WebSocket: the server sends light ticks (new events, clock, score). After every
// "control" message (connect, seek, pause...) and once per match minute we fetch
// the full /state snapshot (momentum, stats, alerts).
// Polling: if the socket cannot open (e.g. a host blocks WebSockets), the browser
// runs its own clock and fetches /state twice a second.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, wsUrl } from '../api/client'
import type { KeyTag, MatchEvent, MatchState, ReplayMessage } from '../api/types'

export type Transport = 'connecting' | 'websocket' | 'polling'

const FEED_LIMIT = 200
const POLL_MS = 500
const CONNECT_TIMEOUT_MS = 8000 // a sleeping free-tier server can take ~1 min; polling also waits

export type Replay = {
  transport: Transport
  t: number
  durationS: number
  playing: boolean
  speed: number
  score: Record<string, number>
  minute: number
  period: number | null
  events: MatchEvent[] // newest last
  tags: Record<string, KeyTag[]> // key-event labels known so far
  snapshot: MatchState | null
  ended: boolean
  error: string | null
  play: () => void
  pause: () => void
  seek: (t: number) => void
  setSpeed: (speed: number) => void
}

export function useReplay(matchId: string, durationS: number, initialSpeed = 10): Replay {
  const [transport, setTransport] = useState<Transport>('connecting')
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeedState] = useState(initialSpeed)
  const [score, setScore] = useState<Record<string, number>>({})
  const [minute, setMinute] = useState(1)
  const [period, setPeriod] = useState<number | null>(null)
  const [events, setEvents] = useState<MatchEvent[]>([])
  const [tags, setTags] = useState<Record<string, KeyTag[]>>({})
  const [snapshot, setSnapshot] = useState<MatchState | null>(null)
  const [ended, setEnded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const socket = useRef<WebSocket | null>(null)
  const latestRequest = useRef(0)
  const lastSnapshotMinute = useRef(-1)
  // Polling-mode clock (refs so the interval sees current values).
  const clock = useRef({ t: 0, playing: false, speed: initialSpeed })
  const initialSpeedRef = useRef(initialSpeed)

  /** Fetch /state at t; ignore responses that arrive after a newer request. */
  const refresh = useCallback(
    async (at: number, replaceFeed: boolean) => {
      const request = ++latestRequest.current
      try {
        const state = await api.state(matchId, at)
        if (request !== latestRequest.current) return
        setSnapshot(state)
        setScore(state.score)
        setMinute(state.minute)
        setPeriod(state.period)
        if (replaceFeed) {
          setEvents(mergeEvents(state.key_events, state.recent_events))
          setTags(state.event_tags)
        } else {
          setTags((known) => mergeTags(known, state.event_tags))
        }
        setError(null)
      } catch (e) {
        if (request === latestRequest.current) setError(e instanceof Error ? e.message : String(e))
      }
    },
    [matchId],
  )

  // --- WebSocket mode, falling back to polling -------------------------------
  useEffect(() => {
    // State starts fresh per match: the parent remounts this hook with key={matchId}.
    let cancelled = false
    let opened = false
    const ws = new WebSocket(wsUrl(`/api/matches/${encodeURIComponent(matchId)}/replay?speed=${initialSpeedRef.current}&from=0`))
    socket.current = ws
    const fallback = () => {
      if (cancelled || opened) return
      cancelled = true
      ws.close()
      socket.current = null
      setTransport('polling')
    }
    const timer = window.setTimeout(fallback, CONNECT_TIMEOUT_MS)

    ws.onopen = () => {
      opened = true
      window.clearTimeout(timer)
      setTransport('websocket')
      ws.send(JSON.stringify({ action: 'pause' })) // start at kick-off; the user presses play
    }
    ws.onerror = fallback
    ws.onclose = () => {
      if (opened && !cancelled) setTransport('polling') // dropped mid-replay: keep going by polling
    }
    ws.onmessage = (message) => {
      const data = JSON.parse(message.data as string) as ReplayMessage
      if (data.type === 'control') {
        clock.current = { t: data.t, playing: !data.paused, speed: data.speed }
        setT(data.t)
        setPlaying(!data.paused)
        setSpeedState(data.speed)
        setEnded(data.t >= data.duration_s)
        lastSnapshotMinute.current = Math.floor(data.t / 60)
        void refresh(data.t, true)
      } else if (data.type === 'tick') {
        clock.current.t = data.t
        setT(data.t)
        setScore(data.score)
        setMinute(data.minute)
        setPeriod(data.period)
        if (data.events.length) setEvents((feed) => mergeEvents(feed, data.events))
        if (Object.keys(data.new_tags).length) setTags((known) => mergeTags(known, data.new_tags))
        const m = Math.floor(data.t / 60)
        if (m !== lastSnapshotMinute.current || data.new_alerts.length) {
          lastSnapshotMinute.current = m
          void refresh(data.t, false)
        }
      } else if (data.type === 'end') {
        setEnded(true)
        setPlaying(false)
        void refresh(data.t, false)
      } else {
        setError(data.detail)
      }
    }

    return () => {
      cancelled = true
      window.clearTimeout(timer)
      ws.onclose = null
      ws.close()
      socket.current = null
    }
  }, [matchId, refresh])

  // --- Polling mode -----------------------------------------------------------
  useEffect(() => {
    if (transport !== 'polling') return
    const endT = durationS + 1
    void refresh(clock.current.t, true)
    const id = window.setInterval(() => {
      const c = clock.current
      if (!c.playing) return
      c.t = Math.min(c.t + (c.speed * POLL_MS) / 1000, endT)
      if (c.t >= endT) {
        c.playing = false
        setPlaying(false)
        setEnded(true)
      }
      setT(c.t)
      void refresh(c.t, true)
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [transport, durationS, refresh])

  // --- Controls (same API in both modes) --------------------------------------
  const send = useCallback((command: object) => {
    const ws = socket.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(command))
      return true
    }
    return false
  }, [])

  const play = useCallback(() => {
    if (send({ action: 'play' })) return
    clock.current.playing = true
    setPlaying(true)
  }, [send])

  const pause = useCallback(() => {
    if (send({ action: 'pause' })) return
    clock.current.playing = false
    setPlaying(false)
  }, [send])

  const seek = useCallback(
    (to: number) => {
      const target = Math.max(0, Math.min(to, durationS + 1))
      if (send({ action: 'seek', t: target })) return
      clock.current.t = target
      setT(target)
      setEnded(target > durationS)
      void refresh(target, true)
    },
    [send, durationS, refresh],
  )

  const setSpeed = useCallback(
    (value: number) => {
      if (send({ action: 'speed', value })) return
      clock.current.speed = value
      setSpeedState(value)
    },
    [send],
  )

  return {
    transport, t, durationS, playing, speed, score, minute, period, events, tags, snapshot, ended, error,
    play, pause, seek, setSpeed,
  }
}

/** Merge event lists by id, ordered by time, keeping the newest FEED_LIMIT. */
function mergeEvents(a: MatchEvent[], b: MatchEvent[]): MatchEvent[] {
  const byId = new Map<string, MatchEvent>()
  for (const e of [...a, ...b]) byId.set(e.event_id, e)
  return [...byId.values()]
    .sort((x, y) => x.timestamp_seconds - y.timestamp_seconds)
    .slice(-FEED_LIMIT)
}

/** Union of labels per event (a pass can be a box entry first and a key pass later). */
function mergeTags(
  known: Record<string, KeyTag[]>,
  incoming: Record<string, KeyTag[]>,
): Record<string, KeyTag[]> {
  const merged = { ...known }
  for (const [eventId, labels] of Object.entries(incoming)) {
    merged[eventId] = [...new Set([...(merged[eventId] ?? []), ...labels])]
  }
  return merged
}

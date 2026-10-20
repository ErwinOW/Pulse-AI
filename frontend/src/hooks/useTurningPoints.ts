import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MatchState, TurningPoint } from '../api/types'

/** Turning points for the goals scored so far (fetched once per new goal, never ahead of time). */
export function useTurningPoints(matchId: string, goals: MatchState['goals']): TurningPoint[] {
  const [byKey, setByKey] = useState<Record<string, TurningPoint[]>>({})
  const lastGoalT = goals.at(-1)?.timestamp_seconds
  const key = lastGoalT === undefined ? '' : `${matchId}|${lastGoalT}`

  useEffect(() => {
    if (lastGoalT === undefined || byKey[key]) return
    const controller = new AbortController()
    // Just after the latest goal: the API only returns goals before t.
    api
      .turningPoints(matchId, lastGoalT + 0.5, controller.signal)
      .then((result) => setByKey((known) => ({ ...known, [key]: result })))
      .catch(() => undefined) // panels stay empty; the rest of the page still works
    return () => controller.abort()
  }, [matchId, lastGoalT, key, byKey])

  return byKey[key] ?? []
}

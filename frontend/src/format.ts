/** Match clock: 3813.7 -> "63:33" (continuous clock, 45:00 = start of the second half). */
export function clockLabel(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

import type { AircraftState } from '@/types/api'

export function fmtCallsign(ac: AircraftState): string {
  return ac.flight?.trim() || ac.registration || ac.hex.toUpperCase()
}

export function fmtAltFt(alt: number | null | undefined): string {
  if (alt == null) return '—'
  return `FL${String(Math.round(alt / 100)).padStart(3, '0')}`
}

export function fmtAltRaw(alt: number | null | undefined): string {
  if (alt == null) return '—'
  return `${alt.toLocaleString()} ft`
}

export function fmtSpeedKt(gs: number | null | undefined): string {
  if (gs == null) return '—'
  return `${Math.round(gs)} kt`
}

export function fmtHeading(trk: number | null | undefined): string {
  if (trk == null) return '—'
  return `${String(Math.round(trk)).padStart(3, '0')}°`
}

export function fmtVsFpm(vs: number | null | undefined): string {
  if (vs == null) return '—'
  if (Math.abs(vs) < 50) return 'LVL'
  const sign = vs > 0 ? '↑' : '↓'
  return `${sign}${Math.abs(Math.round(vs / 10) * 10)}`
}

export function fmtDistanceNm(d: number | null | undefined): string {
  if (d == null) return '—'
  if (d < 10) return `${d.toFixed(1)}nm`
  return `${Math.round(d)}nm`
}

export function fmtBearing(b: number | null | undefined): string {
  if (b == null) return '—'
  return `${String(Math.round(b)).padStart(3, '0')}°`
}

export function fmtAge(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  const diff = Math.max(0, (Date.now() - then) / 1000)
  if (diff < 60) return `${Math.round(diff)}s`
  if (diff < 3600) return `${Math.round(diff / 60)}m`
  if (diff < 86400) return `${Math.round(diff / 3600)}h`
  return `${Math.round(diff / 86400)}d`
}

export function altitudeColor(alt: number | null | undefined): [number, number, number] {
  if (alt == null) return [143, 165, 178]
  if (alt < 5000) return [255, 59, 47]
  if (alt < 10000) return [255, 138, 32]
  if (alt < 20000) return [255, 176, 32]
  if (alt < 30000) return [110, 255, 154]
  if (alt < 40000) return [0, 212, 255]
  return [181, 140, 255]
}

export function altitudeClass(alt: number | null | undefined): string {
  if (alt == null) return 'text-text-mid'
  if (alt < 5000) return 'text-efis-red'
  if (alt < 10000) return 'text-[color:var(--alt-low)]'
  if (alt < 20000) return 'text-efis-amber'
  if (alt < 30000) return 'text-phos-hi'
  if (alt < 40000) return 'text-efis-cyan'
  return 'text-efis-violet'
}

export function isEmergencySquawk(sq: string | null | undefined): boolean {
  return sq === '7500' || sq === '7600' || sq === '7700'
}

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { clsx } from 'clsx'
import { useShallow } from 'zustand/react/shallow'

import { useAircraft, selectAircraftWithPosition } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
import { api } from '@/lib/api'
import { AIRPORTS, haversineNm, type Airport } from '@/lib/airports'
import { fmtAltRaw, fmtSpeedKt, fmtVsFpm } from '@/lib/format'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import type { AircraftState } from '@/types/api'

// Filter knobs — tune if the boards feel sparse / busy.
const RADIUS_NM = 30 // how far around the airport to scan
const APPROACH_VS = -300 // descending faster than this (negative)
const DEPART_VS = 300 // climbing faster than this
const APPROACH_AGL_MAX = 8000 // ft above field
const DEPART_AGL_MAX = 10000

interface Movement {
  hex: string
  callsign: string
  state: AircraftState
  distance_nm: number
  agl_ft: number | null
  origin_icao: string | null
  destination_icao: string | null
  route_label: string | null
}

export function Airports(): React.ReactElement {
  const [icao, setIcao] = useState<string>(AIRPORTS[0].icao)
  const airport = AIRPORTS.find((a) => a.icao === icao) ?? AIRPORTS[0]
  const aircraft = useAircraft(useShallow(selectAircraftWithPosition))

  const { approaching, departing } = useMemo(
    () => bucketTraffic(aircraft, airport),
    [aircraft, airport],
  )

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {/* Airport tabs + summary */}
      <div className="flex flex-wrap items-center gap-3">
        <SectionHeader>AIRPORT TRAFFIC</SectionHeader>
        <div className="flex flex-wrap gap-1">
          {AIRPORTS.map((a) => (
            <button
              key={a.icao}
              type="button"
              onClick={() => setIcao(a.icao)}
              className={clsx(
                'font-mono text-[11px] uppercase tracking-wider px-3 py-1.5 border',
                icao === a.icao
                  ? 'bg-efis-cyan/20 border-efis-cyan text-efis-cyan'
                  : 'border-stroke-hair text-text-mid hover:text-text-hi',
              )}
              title={a.name}
            >
              {a.short}
            </button>
          ))}
        </div>
        <span className="font-mono text-[11px] text-text-low ml-auto">
          {airport.name} ({airport.icao}) · {airport.elev_ft.toLocaleString()} ft elev · within{' '}
          {RADIUS_NM} nm
        </span>
      </div>

      {/* Two side-by-side columns on desktop, stacked on mobile */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        <Column
          title="APPROACHING"
          accent="text-efis-phos border-efis-phos"
          rows={approaching}
          empty="No aircraft on approach right now."
          showVs
        />
        <Column
          title="DEPARTING"
          accent="text-efis-amber border-efis-amber"
          rows={departing}
          empty="No aircraft departing right now."
          showVs
        />
      </div>

      {/* Footer hint */}
      <div className="font-mono text-[10px] text-text-low text-center pt-2">
        Filter: descending&nbsp;
        {APPROACH_VS}&nbsp;fpm or steeper, alt AGL &lt;&nbsp;{APPROACH_AGL_MAX.toLocaleString()} ft for
        APPROACHING · climbing&nbsp;{DEPART_VS}&nbsp;fpm or faster, alt AGL &lt;&nbsp;
        {DEPART_AGL_MAX.toLocaleString()} ft for DEPARTING. Click any row to track on radar.
      </div>
    </div>
  )
}

function bucketTraffic(
  aircraft: AircraftState[],
  airport: Airport,
): { approaching: Movement[]; departing: Movement[] } {
  const approaching: Movement[] = []
  const departing: Movement[] = []
  for (const a of aircraft) {
    if (a.lat == null || a.lon == null) continue
    const distance_nm = haversineNm(airport.lat, airport.lon, a.lat, a.lon)
    if (distance_nm > RADIUS_NM) continue
    const agl_ft = a.alt_baro != null ? a.alt_baro - airport.elev_ft : null

    const m: Movement = {
      hex: a.hex,
      callsign: a.flight?.trim() || a.registration?.trim() || a.hex.toUpperCase(),
      state: a,
      distance_nm,
      agl_ft,
      origin_icao: null,
      destination_icao: null,
      route_label: null,
    }

    if (a.baro_rate != null && agl_ft != null) {
      if (a.baro_rate <= APPROACH_VS && agl_ft <= APPROACH_AGL_MAX && agl_ft >= -200) {
        approaching.push(m)
        continue
      }
      if (a.baro_rate >= DEPART_VS && agl_ft <= DEPART_AGL_MAX && agl_ft >= -200) {
        departing.push(m)
      }
    }
  }
  approaching.sort((a, b) => a.distance_nm - b.distance_nm)
  departing.sort((a, b) => a.distance_nm - b.distance_nm)
  return { approaching, departing }
}

// Shared column template — keep MovementRow's gridTemplateColumns in sync.
const ROW_COLS = 'minmax(70px, 1fr) 60px 70px 70px 70px minmax(0, 1.4fr)'

function Column({
  title,
  accent,
  rows,
  empty,
  showVs,
}: {
  title: string
  accent: string
  rows: Movement[]
  empty: string
  showVs?: boolean
}): React.ReactElement {
  return (
    <div className="bg-bg-1 border border-stroke-hair">
      <div className={clsx('px-3 py-2 border-b font-mono text-[12px] tracking-wider', accent)}>
        {title} <span className="text-text-low">({rows.length})</span>
      </div>
      {rows.length === 0 ? (
        <div className="px-3 py-8 text-center font-mono text-[11px] text-text-low">{empty}</div>
      ) : (
        <>
          {/* Column headers — same grid template as the rows below so columns
           *  line up under their labels. */}
          <div
            className="grid gap-2 items-center px-3 py-1.5 border-b border-stroke-hair font-mono text-[10px] text-text-low uppercase tracking-wider"
            style={{ gridTemplateColumns: ROW_COLS }}
          >
            <span>Call</span>
            <span>Type</span>
            <span>Alt AGL</span>
            {showVs ? <span>V/S</span> : <span />}
            <span>Dist</span>
            <span>Route · Speed</span>
          </div>
          <div>
            {rows.map((m) => (
              <MovementRow key={m.hex} m={m} showVs={showVs} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function MovementRow({ m, showVs }: { m: Movement; showVs?: boolean }): React.ReactElement {
  const navigate = useNavigate()
  const select = useSelection((s) => s.select)
  const onClick = () => {
    select(m.hex.toLowerCase(), { focus: true })
    navigate('/')
  }

  // Pull route enrichment lazily (cached 6h server-side) so we can show
  // "from KORD" or "to KSFO" alongside the basic position info. Falls back
  // to the live data if the route isn't found.
  const { data: route } = useQuery({
    queryKey: ['route', m.hex],
    queryFn: () => api.route(m.hex),
    enabled: Boolean(m.callsign),
    staleTime: 6 * 60 * 60_000,
    gcTime: 24 * 60 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const fromTo = route
    ? [route.origin?.iata ?? route.origin?.icao, route.destination?.iata ?? route.destination?.icao]
        .filter(Boolean)
        .join(' → ')
    : null

  return (
    <div
      onClick={onClick}
      className="grid gap-2 items-center px-3 py-2 border-b border-stroke-hair last:border-b-0 cursor-pointer hover:bg-bg-2"
      style={{ gridTemplateColumns: ROW_COLS }}
    >
      <span className="font-mono text-[12px] text-efis-white truncate">{m.callsign}</span>
      <span className="font-mono text-[10px] text-text-mid uppercase">
        {m.state.type_code ?? '—'}
      </span>
      <span className="font-mono text-[11px] text-text-mid tabular-nums">
        {m.agl_ft != null ? `${fmtAltRaw(m.agl_ft)}` : '—'}
      </span>
      {showVs && (
        <span className="font-mono text-[11px] text-text-mid tabular-nums">
          {fmtVsFpm(m.state.baro_rate)}
        </span>
      )}
      <span className="font-mono text-[11px] text-text-mid tabular-nums">
        {m.distance_nm.toFixed(1)} nm
      </span>
      <span className="font-mono text-[11px] text-text-low truncate">
        {fromTo ? <span className="text-efis-cyan">{fromTo}</span> : ''}
        {fromTo && m.state.gs ? ' · ' : ''}
        {m.state.gs ? `${fmtSpeedKt(m.state.gs)}` : ''}
      </span>
    </div>
  )
}

import { memo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { clsx } from 'clsx'

import { useSelection } from '@/store/selection'
import { api } from '@/lib/api'
import { fmtAltRaw, fmtSpeedKt, fmtVsFpm } from '@/lib/format'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import type { AirportMovement } from '@/types/api'

const RADIUS_NM = 30
const APPROACH_VS = -300
const DEPART_VS = 300
const APPROACH_AGL_MAX = 8000
const DEPART_AGL_MAX = 10000

const ROW_COLS =
  'minmax(70px, 1fr) 60px 70px 70px 70px minmax(0, 1.4fr)'

export function Airports(): React.ReactElement {
  // Backend computes the buckets — uses route_cache (origin/destination) when
  // available so an aircraft heading to KDEN that's currently passing closer
  // to KAPA still ends up on KDEN's board. Falls back to closest-airport for
  // GA aircraft with no route data.
  const { data, isLoading } = useQuery({
    queryKey: ['airports-traffic'],
    queryFn: () => api.airportsTraffic(),
    refetchInterval: 5_000,
    staleTime: 3_000,
    // Keep showing the previous data during a refetch instead of unmounting
    // the table. Combined with the row-level React.memo below, unchanged
    // rows don't re-render at all on each tick — only cells whose values
    // actually moved get repainted.
    placeholderData: keepPreviousData,
  })

  const airports = data?.airports ?? []
  const [icao, setIcao] = useState<string>('KDEN')
  const airport = airports.find((a) => a.icao === icao) ?? airports[0]
  const buckets = data?.by_icao[icao] ?? { approaching: [], departing: [] }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SectionHeader>AIRPORT TRAFFIC</SectionHeader>
        <div className="flex flex-wrap gap-1">
          {airports.map((a) => {
            const total =
              (data?.by_icao[a.icao]?.approaching.length ?? 0) +
              (data?.by_icao[a.icao]?.departing.length ?? 0)
            return (
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
                {a.short} ({total})
              </button>
            )
          })}
        </div>
        {airport && (
          <span className="font-mono text-[11px] text-text-low ml-auto">
            {airport.name} ({airport.icao}) · {airport.elev_ft.toLocaleString()} ft elev · within{' '}
            {RADIUS_NM} nm
          </span>
        )}
      </div>

      {isLoading && <div className="text-text-mid font-mono text-sm">Loading…</div>}

      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        <Column
          title="APPROACHING"
          accent="text-efis-phos border-efis-phos"
          rows={buckets.approaching}
          empty="No aircraft on approach right now."
        />
        <Column
          title="DEPARTING"
          accent="text-efis-amber border-efis-amber"
          rows={buckets.departing}
          empty="No aircraft departing right now."
        />
      </div>

      <div className="font-mono text-[10px] text-text-low text-center pt-2">
        Aircraft are bucketed by their route data (origin/destination) when
        available, falling back to the closest airport for GA traffic without a
        flight plan. Filter: descending&nbsp;{APPROACH_VS}&nbsp;fpm or steeper
        + alt AGL &lt;&nbsp;{APPROACH_AGL_MAX.toLocaleString()} ft for APPROACHING ·
        climbing&nbsp;{DEPART_VS}&nbsp;fpm or faster + alt AGL &lt;&nbsp;
        {DEPART_AGL_MAX.toLocaleString()} ft for DEPARTING. Click any row to
        track on radar.
      </div>
    </div>
  )
}

function Column({
  title,
  accent,
  rows,
  empty,
}: {
  title: string
  accent: string
  rows: AirportMovement[]
  empty: string
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
          <div
            className="grid gap-2 items-center px-3 py-1.5 border-b border-stroke-hair font-mono text-[10px] text-text-low uppercase tracking-wider"
            style={{ gridTemplateColumns: ROW_COLS }}
          >
            <span>Call</span>
            <span>Type</span>
            <span>Alt AGL</span>
            <span>V/S</span>
            <span>Dist</span>
            <span>Route · Speed</span>
          </div>
          <div>
            {rows.map((m) => (
              <MovementRow key={m.hex} m={m} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Memoized so unchanged rows don't re-render every refetch. Each refetch
 * deserializes a NEW AircraftMovement object with same field values, so the
 * default reference equality misses — explicit field-by-field check ensures
 * a row only repaints when something the user can actually see has changed.
 */
const MovementRow = memo(
  function MovementRow({ m }: { m: AirportMovement }): React.ReactElement {
  const navigate = useNavigate()
  const select = useSelection((s) => s.select)
  const onClick = () => {
    select(m.hex.toLowerCase(), { focus: true })
    navigate('/')
  }

  const fromTo =
    m.origin_icao || m.destination_icao
      ? `${m.origin_icao ?? '?'} → ${m.destination_icao ?? '?'}`
      : null

  return (
    <div
      onClick={onClick}
      className="grid gap-2 items-center px-3 py-2 border-b border-stroke-hair last:border-b-0 cursor-pointer hover:bg-bg-2"
      style={{ gridTemplateColumns: ROW_COLS }}
      title={
        m.from_route_data
          ? 'Bucketed from route data — origin/destination matches this airport'
          : 'No route data — bucketed by closest airport'
      }
    >
      <span className="font-mono text-[12px] text-efis-white truncate">{m.callsign}</span>
      <span className="font-mono text-[10px] text-text-mid uppercase">{m.type_code ?? '—'}</span>
      <span className="font-mono text-[11px] text-text-mid tabular-nums">
        {m.agl_ft != null ? fmtAltRaw(m.agl_ft) : '—'}
      </span>
      <span className="font-mono text-[11px] text-text-mid tabular-nums">
        {fmtVsFpm(m.baro_rate)}
      </span>
      <span className="font-mono text-[11px] text-text-mid tabular-nums">
        {m.distance_nm.toFixed(1)} nm
      </span>
      <span className="font-mono text-[11px] text-text-low truncate">
        {fromTo && (
          <span className={m.from_route_data ? 'text-efis-cyan' : 'text-text-low italic'}>
            {fromTo}
          </span>
        )}
        {fromTo && m.gs ? ' · ' : ''}
        {m.gs ? fmtSpeedKt(m.gs) : ''}
      </span>
    </div>
  )
  },
  (prev, next) =>
    prev.m.hex === next.m.hex &&
    prev.m.callsign === next.m.callsign &&
    prev.m.type_code === next.m.type_code &&
    prev.m.alt_baro === next.m.alt_baro &&
    prev.m.agl_ft === next.m.agl_ft &&
    prev.m.baro_rate === next.m.baro_rate &&
    prev.m.gs === next.m.gs &&
    // Distance changes by inches every tick — round to 0.1 nm so we don't
    // re-render on sub-meaningful movement.
    Math.round(prev.m.distance_nm * 10) === Math.round(next.m.distance_nm * 10) &&
    prev.m.origin_icao === next.m.origin_icao &&
    prev.m.destination_icao === next.m.destination_icao &&
    prev.m.from_route_data === next.m.from_route_data,
)

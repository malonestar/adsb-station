import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Panel } from '@/components/chrome/Panel'
import { Button } from '@/components/chrome/Button'
import { DataCell } from '@/components/chrome/DataCell'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import { useAircraft } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
import { useHistory } from '@/store/history'
import {
  altitudeClass,
  fmtAltFt,
  fmtAltRaw,
  fmtBearing,
  fmtCallsign,
  fmtDistanceNm,
  fmtHeading,
  fmtSpeedKt,
  fmtVsFpm,
  isEmergencySquawk,
} from '@/lib/format'
import { api } from '@/lib/api'
import { useToggleWatch } from '@/lib/watchlist'
import type { RouteInfo, RouteSource } from '@/types/api'
import { clsx } from 'clsx'

const ROUTE_SOURCE_LABEL: Record<RouteSource, string> = {
  adsbdb: 'via adsbdb',
  hexdb: 'via hexdb',
  aeroapi: 'via FlightAware',
  not_found: 'no route data',
  no_callsign: 'no callsign',
  unavailable: 'route lookup unavailable',
}

function RouteBlock({ route }: { route: RouteInfo }): React.ReactElement | null {
  const hasRoute = Boolean(route.origin || route.destination)
  if (!hasRoute) return null

  const oIata = route.origin?.iata
  const dIata = route.destination?.iata
  const oIcao = route.origin?.icao
  const dIcao = route.destination?.icao
  // Prefer IATA for the big codes (more recognizable), fall back to ICAO.
  const oCode = oIata ?? oIcao ?? '???'
  const dCode = dIata ?? dIcao ?? '???'

  return (
    <div className="pt-2 border-t border-stroke-hair">
      <SectionHeader className="mb-1">ROUTE</SectionHeader>
      <div className="font-mono text-lg text-efis-cyan leading-tight tabular-nums">
        {oCode} <span className="text-text-mid">→</span> {dCode}
      </div>
      <div className="font-mono text-[11px] text-text-mid mt-0.5 leading-snug">
        {route.origin ? (
          <>
            {route.origin.name}
            {route.origin.icao && (
              <span className="text-text-low">
                {' '}
                ({route.origin.icao}
                {route.origin.iata ? ` / ${route.origin.iata}` : ''})
              </span>
            )}
          </>
        ) : (
          <span className="text-text-low">origin unknown</span>
        )}
        <span className="text-text-low"> → </span>
        {route.destination ? (
          <>
            {route.destination.name}
            {route.destination.icao && (
              <span className="text-text-low">
                {' '}
                ({route.destination.icao}
                {route.destination.iata ? ` / ${route.destination.iata}` : ''})
              </span>
            )}
          </>
        ) : (
          <span className="text-text-low">destination unknown</span>
        )}
      </div>
      {route.airline && (
        <div className="font-mono text-[11px] text-text-mid">{route.airline}</div>
      )}
      <div className="font-mono text-[10px] text-text-low mt-0.5">
        {ROUTE_SOURCE_LABEL[route.source]}
      </div>
    </div>
  )
}

export function AircraftDetail(): React.ReactElement {
  const hex = useSelection((s) => s.selectedHex)
  const clear = useSelection((s) => s.clear)
  const live = useAircraft((s) => (hex ? s.byHex[hex] : null))
  const historyHex = useHistory((s) => s.historyHex)
  const toggleHistoryHex = useHistory((s) => s.toggleHistoryHex)
  const historyActive = Boolean(hex) && historyHex === hex

  const { data: detail } = useQuery({
    queryKey: ['aircraft', hex],
    queryFn: () => (hex ? api.aircraftDetail(hex) : Promise.resolve(null)),
    enabled: Boolean(hex),
    refetchInterval: 3_000,
    staleTime: 2_500,
  })

  const watchLabel = live?.flight?.trim() || (detail?.catalog as { registration?: string } | null)?.registration || undefined
  const { watching, toggle: toggleWatch, isPending: watchPending } = useToggleWatch(hex, watchLabel)
  const followSelection = useSelection((s) => s.followSelection)
  const toggleFollow = useSelection((s) => s.toggleFollow)
  const tracking = followSelection && Boolean(hex)

  const { data: route } = useQuery({
    queryKey: ['route', hex],
    queryFn: () => (hex ? api.route(hex) : Promise.resolve(null)),
    enabled: Boolean(hex),
    staleTime: 6 * 60 * 60_000, // 6h — matches backend cache
    gcTime: 24 * 60 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  })

  return (
    <AnimatePresence mode="wait">
      {hex && (
        <motion.div
          key={hex}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 24 }}
          transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
          className="h-full overflow-y-auto"
        >
          <Panel
            title={live ? fmtCallsign(live) : hex.toUpperCase()}
            action={
              // Larger touch target on mobile (~44px) — plain button, ignores
              // the sm-Button padding so it can be square.
              <button
                type="button"
                onClick={clear}
                title="Close"
                aria-label="Close detail panel"
                className="w-11 h-11 lg:w-8 lg:h-8 flex items-center justify-center text-text-mid hover:text-efis-cyan active:text-efis-cyan -mr-2 lg:-mr-1"
              >
                <span className="text-base lg:text-sm">✕</span>
              </button>
            }
            padded={false}
            active
            className="h-full"
          >
            {/* Photo — 1px horizontal inset so the active-panel cyan glow stays visible */}
            {(detail?.catalog as { photo_url?: string } | null)?.photo_url && (
              <a
                href={((detail?.catalog as { photo_link?: string })?.photo_link) ?? '#'}
                target="_blank"
                rel="noreferrer"
                className="block px-px"
              >
                <img
                  src={(detail!.catalog as { photo_url: string }).photo_url}
                  alt={hex}
                  className="w-full aspect-[16/9] object-cover border-b border-stroke-hair"
                />
              </a>
            )}

            <div className="p-3 space-y-3">
              {/* ID block */}
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-xl text-efis-white">
                    {live ? fmtCallsign(live) : hex.toUpperCase()}
                  </span>
                  {live?.is_military && (
                    <span className="font-mono text-[10px] px-2 py-0.5 border border-efis-amber text-efis-amber">
                      MIL
                    </span>
                  )}
                  {live && isEmergencySquawk(live.squawk) && (
                    <span className="font-mono text-[10px] px-2 py-0.5 border border-efis-red text-efis-red animate-pulse">
                      SQ {live.squawk}
                    </span>
                  )}
                </div>
                <div className="font-mono text-[11px] text-text-mid mt-0.5">
                  {live?.registration ?? (detail?.catalog as { registration?: string } | null)?.registration ?? ''}{' '}
                  &middot;{' '}
                  {live?.type_code ?? (detail?.catalog as { type_code?: string } | null)?.type_code ?? ''}{' '}
                  &middot; {hex.toUpperCase()}
                </div>
                {(detail?.catalog as { operator?: string } | null)?.operator && (
                  <div className="font-mono text-[11px] text-text-mid">
                    {(detail?.catalog as { operator?: string }).operator}
                  </div>
                )}
              </div>

              {/* Flight data */}
              {live && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <DataCell
                      label="ALT"
                      value={fmtAltFt(live.alt_baro)}
                      unit={live.alt_baro != null ? fmtAltRaw(live.alt_baro) : undefined}
                      accent={live.alt_baro != null && live.alt_baro >= 30000 ? 'cyan' : 'phos'}
                    />
                    <DataCell
                      label="V/S"
                      value={fmtVsFpm(live.baro_rate)}
                      unit="fpm"
                    />
                    <DataCell label="SPD" value={fmtSpeedKt(live.gs)} />
                    <DataCell label="HDG" value={fmtHeading(live.track)} />
                    <DataCell label="DIST" value={fmtDistanceNm(live.distance_nm)} accent="cyan" />
                    <DataCell label="BRG" value={fmtBearing(live.bearing_deg)} />
                  </div>

                  <div className={clsx('font-mono text-sm', altitudeClass(live.alt_baro))}>
                    SQ {live.squawk ?? '----'} &middot; RSSI{' '}
                    {live.rssi != null ? live.rssi.toFixed(1) : '—'}dBFS
                  </div>
                </>
              )}

              {route && <RouteBlock route={route} />}

              <div className="flex gap-2 pt-2 border-t border-stroke-hair">
                <Button
                  variant={tracking ? 'primary' : 'ghost'}
                  onClick={toggleFollow}
                  disabled={!hex || !live?.lat || !live?.lon}
                  title={
                    !live?.lat
                      ? 'Aircraft has no position yet'
                      : tracking
                        ? 'Stop following — map will stop auto-centering'
                        : 'Follow this aircraft — map auto-centers as it moves'
                  }
                  className={clsx(
                    'px-4 py-2 lg:px-3 lg:py-1.5 text-xs',
                    tracking && 'bg-efis-cyan/20 border-efis-cyan text-efis-cyan hover:border-efis-cyan',
                  )}
                >
                  {tracking ? 'TRACKING ✓' : 'TRACK'}
                </Button>
                <Button
                  variant={watching ? 'primary' : 'ghost'}
                  onClick={toggleWatch}
                  disabled={!hex || watchPending}
                  title={watching ? 'Remove from watchlist' : 'Add to watchlist'}
                  className={clsx(
                    'px-4 py-2 lg:px-3 lg:py-1.5 text-xs',
                    watching && 'bg-efis-amber/20 border-efis-amber text-efis-amber hover:border-efis-amber',
                  )}
                >
                  {watching ? 'WATCHING ✓' : 'WATCH'}
                </Button>
                <Button
                  variant={historyActive ? 'primary' : 'ghost'}
                  onClick={() => hex && toggleHistoryHex(hex)}
                  className={clsx(
                    'px-4 py-2 lg:px-3 lg:py-1.5 text-xs',
                    historyActive &&
                      'bg-efis-violet/20 border-efis-violet text-efis-violet hover:border-efis-violet',
                  )}
                >
                  HISTORY
                </Button>
              </div>
            </div>
          </Panel>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

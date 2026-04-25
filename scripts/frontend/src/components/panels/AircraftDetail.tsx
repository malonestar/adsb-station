import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Panel } from '@/components/chrome/Panel'
import { Button } from '@/components/chrome/Button'
import { DataCell } from '@/components/chrome/DataCell'
import { useAircraft } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
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
import { clsx } from 'clsx'

export function AircraftDetail(): React.ReactElement {
  const hex = useSelection((s) => s.selectedHex)
  const clear = useSelection((s) => s.clear)
  const live = useAircraft((s) => (hex ? s.byHex[hex] : null))

  const { data: detail } = useQuery({
    queryKey: ['aircraft', hex],
    queryFn: () => (hex ? api.aircraftDetail(hex) : Promise.resolve(null)),
    enabled: Boolean(hex),
    staleTime: 30_000,
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
              <Button size="sm" variant="ghost" onClick={clear}>
                ✕
              </Button>
            }
            padded={false}
            active
            className="h-full"
          >
            {/* Photo */}
            {(detail?.catalog as { photo_url?: string } | null)?.photo_url && (
              <a
                href={((detail?.catalog as { photo_link?: string })?.photo_link) ?? '#'}
                target="_blank"
                rel="noreferrer"
                className="block"
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

              <div className="flex gap-2 pt-2 border-t border-stroke-hair">
                <Button variant="primary" size="sm">TRACK</Button>
                <Button variant="ghost" size="sm">WATCH</Button>
              </div>
            </div>
          </Panel>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

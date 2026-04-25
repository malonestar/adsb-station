import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '@/lib/api'
import { RadarMap } from '@/components/map/RadarMap'
import { useAircraft } from '@/store/aircraft'
import { useAlerts, selectActiveAlerts } from '@/store/alerts'
import { useSelection } from '@/store/selection'
import { useStats } from '@/store/stats'
import { useAdsbSocket } from '@/lib/ws'
import { fmtAltFt, fmtCallsign, fmtDistanceNm, fmtSpeedKt } from '@/lib/format'

export function Kiosk(): React.ReactElement {
  useAdsbSocket()
  const { data: receiver } = useQuery({
    queryKey: ['receiver'],
    queryFn: () => api.receiver(),
    staleTime: 60_000,
  })
  const total = useAircraft((s) => Object.keys(s.byHex).length)
  const max = useStats((s) => s.current?.max_range_nm_today ?? 0)
  const selected = useSelection((s) => s.selectedHex)
  const selectedAc = useAircraft((s) => (selected ? s.byHex[selected] : null))
  const clear = useSelection((s) => s.clear)
  const alerts = useAlerts(selectActiveAlerts)

  // Auto-dismiss selection after 30s
  useEffect(() => {
    if (!selected) return
    const t = setTimeout(() => clear(), 30_000)
    return () => clearTimeout(t)
  }, [selected, clear])

  const station = { lat: receiver?.lat ?? 39.7, lon: receiver?.lon ?? -104.8 }

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-0 overflow-hidden">
      <header
        className="flex items-center justify-between px-4 border-b border-stroke-hair bg-bg-1 font-mono text-xs"
        style={{ height: 'var(--kiosk-topbar-h)' }}
      >
        <span className="text-efis-cyan uppercase">{receiver?.name ?? 'STATION'}</span>
        <UtcClock />
        <span>A/C {total}</span>
        <span>MAX {max.toFixed(0)}nm</span>
      </header>

      <div className="flex-1 relative min-h-0">
        <RadarMap station={station} />

        <AnimatePresence>
          {selectedAc && (
            <motion.aside
              key={selected}
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
              className="absolute top-0 right-0 bottom-0 bg-bg-1 border-l border-stroke-hair p-4 flex flex-col gap-3"
              style={{ width: 'var(--kiosk-panel-w)' }}
            >
              <div className="font-mono text-2xl text-efis-white">{fmtCallsign(selectedAc)}</div>
              <div className="font-mono text-sm text-text-mid">
                {selectedAc.registration ?? ''} · {selectedAc.type_code ?? ''}
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <Stat label="DIST" value={fmtDistanceNm(selectedAc.distance_nm)} />
                <Stat label="ALT" value={fmtAltFt(selectedAc.alt_baro)} />
                <Stat label="SPD" value={fmtSpeedKt(selectedAc.gs)} />
                <Stat label="HDG" value={`${Math.round(selectedAc.track ?? 0)}°`} />
              </div>
              <button
                onClick={clear}
                className="mt-auto font-mono text-xs uppercase py-3 border border-stroke-hair text-text-mid hover:text-efis-cyan hover:border-efis-cyan"
              >
                DISMISS
              </button>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {alerts.length > 0 && (
        <div className="flex items-center gap-4 px-4 border-t border-efis-red bg-efis-red/10 text-efis-red font-mono text-xs h-12 overflow-hidden">
          <span className="animate-pulse">●</span>
          <span>{alerts.length} ACTIVE</span>
          <div className="overflow-hidden flex gap-6">
            {alerts.slice(0, 5).map((a) => (
              <span key={a.id} className="uppercase whitespace-nowrap">
                {a.kind} · {a.hex.toUpperCase()}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div>
      <div className="section-header text-[10px]">{label}</div>
      <div className="font-mono text-lg">{value}</div>
    </div>
  )
}

function UtcClock(): React.ReactElement {
  const [now, setNow] = useState<string>(new Date().toISOString().slice(11, 19) + 'Z')
  useEffect(() => {
    const t = setInterval(() => setNow(new Date().toISOString().slice(11, 19) + 'Z'), 1000)
    return () => clearInterval(t)
  }, [])
  return <span className="text-efis-amber">{now}</span>
}

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { useShallow } from 'zustand/react/shallow'
import { api } from '@/lib/api'
import { RadarMap } from '@/components/map/RadarMap'
import { useAircraft } from '@/store/aircraft'
import { useAlerts, selectActiveAlerts } from '@/store/alerts'
import { useSelection } from '@/store/selection'
import { useStats } from '@/store/stats'
import { useAdsbSocket } from '@/lib/ws'
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
import { clsx } from 'clsx'

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
  const clear = useSelection((s) => s.clear)
  const alerts = useAlerts(useShallow(selectActiveAlerts))

  // Auto-dismiss selection after 60s of no interaction
  useEffect(() => {
    if (!selected) return
    const t = setTimeout(() => clear(), 60_000)
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
        <span>
          <span className="text-text-low">A/C </span>
          <span className="text-efis-white">{total}</span>
        </span>
        <span>
          <span className="text-text-low">MAX </span>
          {max.toFixed(0)}nm
        </span>
      </header>

      <div className="flex-1 relative min-h-0">
        <RadarMap
          station={station}
          rightControlsOffset={selected ? 296 : 0}
        />
        <AnimatePresence>
          {selected && <KioskDetailDrawer hex={selected} onClose={clear} />}
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

// ─── Detail drawer (touch-optimized, scrollable) ─────────────────────────
function KioskDetailDrawer({
  hex,
  onClose,
}: {
  hex: string
  onClose: () => void
}): React.ReactElement {
  const live = useAircraft((s) => s.byHex[hex])
  const { data: detail } = useQuery({
    queryKey: ['aircraft', hex],
    queryFn: () => api.aircraftDetail(hex),
    staleTime: 30_000,
  })

  const cat = (detail?.catalog as CatalogLike | null) ?? null
  const photo = cat?.photo_url ?? null

  return (
    <motion.aside
      key={hex}
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
      className="absolute top-0 right-0 bottom-0 bg-bg-1 border-l border-stroke-hair flex flex-col overflow-hidden"
      style={{ width: 'var(--kiosk-panel-w)' }}
    >
      {/* Close bar — extra tall for touch */}
      <button
        onClick={onClose}
        className="w-full h-14 border-b border-stroke-hair font-mono text-sm uppercase tracking-wider text-text-mid hover:text-efis-cyan active:text-efis-white bg-bg-2"
      >
        ✕ DISMISS
      </button>

      <div className="flex-1 overflow-y-auto overscroll-contain">
        {/* Photo */}
        {photo && (
          <img
            src={photo}
            alt={hex}
            className="w-full aspect-[16/9] object-cover border-b border-stroke-hair"
          />
        )}

        {/* ID block */}
        <div className="p-4 border-b border-stroke-hair">
          <div className="font-mono text-2xl text-efis-white leading-none">
            {live ? fmtCallsign(live) : hex.toUpperCase()}
          </div>
          <div className="font-mono text-xs text-text-mid mt-2 space-y-1">
            {(live?.registration ?? cat?.registration) && (
              <div>{live?.registration ?? cat?.registration}</div>
            )}
            {(live?.type_code ?? cat?.type_code) && (
              <div>{live?.type_code ?? cat?.type_code}{cat?.type_name && ` · ${cat.type_name}`}</div>
            )}
            {cat?.operator && <div className="text-text-hi">{cat.operator}</div>}
            {cat?.manufacturer && cat.manufacturer !== cat.operator && (
              <div className="text-text-low">{cat.manufacturer}</div>
            )}
            <div className="text-text-low pt-1">HEX {hex.toUpperCase()}</div>
          </div>

          {/* Badges */}
          <div className="flex gap-2 mt-3 flex-wrap">
            {live?.is_military && (
              <Badge color="amber">MIL</Badge>
            )}
            {live?.is_interesting && !live.is_military && (
              <Badge color="violet">INT</Badge>
            )}
            {live && isEmergencySquawk(live.squawk) && (
              <Badge color="red" pulse>SQ {live.squawk}</Badge>
            )}
          </div>
        </div>

        {/* Flight data */}
        {live && (
          <div className="p-4 border-b border-stroke-hair">
            <SectionHeader>FLIGHT</SectionHeader>
            <div className="grid grid-cols-2 gap-3 mt-2">
              <BigStat
                label="ALT"
                value={fmtAltFt(live.alt_baro)}
                sub={live.alt_baro != null ? fmtAltRaw(live.alt_baro) : undefined}
                className={altitudeClass(live.alt_baro)}
              />
              <BigStat
                label="V/S"
                value={fmtVsFpm(live.baro_rate)}
                sub="fpm"
              />
              <BigStat label="SPD" value={fmtSpeedKt(live.gs)} />
              <BigStat label="HDG" value={fmtHeading(live.track)} />
              <BigStat label="DIST" value={fmtDistanceNm(live.distance_nm)} accent />
              <BigStat label="BRG" value={fmtBearing(live.bearing_deg)} />
            </div>
          </div>
        )}

        {/* Signal + squawk */}
        {live && (
          <div className="p-4 border-b border-stroke-hair">
            <SectionHeader>SIGNAL</SectionHeader>
            <div className="grid grid-cols-2 gap-3 mt-2 font-mono text-sm">
              <div>
                <div className="text-text-low text-[10px] uppercase">SQUAWK</div>
                <div className="text-text-hi">{live.squawk ?? '----'}</div>
              </div>
              <div>
                <div className="text-text-low text-[10px] uppercase">RSSI</div>
                <div className="text-text-hi">
                  {live.rssi != null ? `${live.rssi.toFixed(1)} dBFS` : '—'}
                </div>
              </div>
              <div>
                <div className="text-text-low text-[10px] uppercase">MSGS</div>
                <div className="text-text-hi">{live.messages.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-text-low text-[10px] uppercase">SEEN</div>
                <div className="text-text-hi">{live.seen.toFixed(1)}s</div>
              </div>
            </div>
          </div>
        )}

        {/* Catalog extras */}
        {cat && (cat.first_seen || cat.min_distance_nm != null || cat.max_alt_ft != null) && (
          <div className="p-4 border-b border-stroke-hair">
            <SectionHeader>HISTORY</SectionHeader>
            <div className="mt-2 font-mono text-xs space-y-1 text-text-mid">
              {cat.seen_count != null && (
                <div>
                  <span className="text-text-low">SEEN </span>
                  <span className="text-text-hi">{cat.seen_count}×</span>
                </div>
              )}
              {cat.min_distance_nm != null && (
                <div>
                  <span className="text-text-low">CLOSEST </span>
                  <span className="text-text-hi">{cat.min_distance_nm.toFixed(1)}nm</span>
                </div>
              )}
              {cat.max_alt_ft != null && (
                <div>
                  <span className="text-text-low">MAX ALT </span>
                  <span className="text-text-hi">FL{String(Math.round(cat.max_alt_ft / 100)).padStart(3, '0')}</span>
                </div>
              )}
              {cat.max_speed_kt != null && (
                <div>
                  <span className="text-text-low">MAX SPD </span>
                  <span className="text-text-hi">{cat.max_speed_kt}kt</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Photo credit */}
        {cat?.photo_photographer && (
          <div className="p-4 font-mono text-[10px] text-text-low">
            Photo © {cat.photo_photographer}
            {cat.photo_link && (
              <>
                {' · '}
                <a
                  href={cat.photo_link}
                  target="_blank"
                  rel="noreferrer"
                  className="text-text-mid hover:text-efis-cyan underline"
                >
                  Planespotters
                </a>
              </>
            )}
          </div>
        )}
      </div>
    </motion.aside>
  )
}

// ─── UI helpers ──────────────────────────────────────────────────────────

interface CatalogLike {
  registration?: string | null
  type_code?: string | null
  type_name?: string | null
  operator?: string | null
  manufacturer?: string | null
  photo_url?: string | null
  photo_thumb_url?: string | null
  photo_photographer?: string | null
  photo_link?: string | null
  first_seen?: string | null
  seen_count?: number | null
  min_distance_nm?: number | null
  max_alt_ft?: number | null
  max_speed_kt?: number | null
}

function BigStat({
  label,
  value,
  sub,
  accent,
  className,
}: {
  label: string
  value: string
  sub?: string
  accent?: boolean
  className?: string
}): React.ReactElement {
  return (
    <div>
      <div className="text-text-low font-mono text-[10px] uppercase tracking-wider">{label}</div>
      <div
        className={clsx(
          'font-mono text-xl leading-tight tabular-nums mt-0.5',
          className ?? (accent ? 'text-efis-cyan' : 'text-text-hi'),
        )}
      >
        {value}
      </div>
      {sub && <div className="text-text-low font-mono text-[10px] mt-0.5">{sub}</div>}
    </div>
  )
}

function SectionHeader({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <h3 className="font-mono text-[10px] tracking-[0.08em] text-text-low uppercase">{children}</h3>
  )
}

function Badge({
  color,
  pulse,
  children,
}: {
  color: 'amber' | 'red' | 'violet'
  pulse?: boolean
  children: React.ReactNode
}): React.ReactElement {
  const cls = {
    amber: 'border-efis-amber text-efis-amber',
    red: 'border-efis-red text-efis-red',
    violet: 'border-efis-violet text-efis-violet',
  }[color]
  return (
    <span
      className={clsx(
        'inline-block font-mono text-[10px] px-2 py-0.5 border tracking-wider',
        cls,
        pulse && 'animate-pulse',
      )}
    >
      {children}
    </span>
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

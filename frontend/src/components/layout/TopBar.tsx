import { useEffect, useMemo, useState } from 'react'
import { NavLink } from 'react-router'
import { useAircraft } from '@/store/aircraft'
import { useAlerts } from '@/store/alerts'
import { useStats } from '@/store/stats'
import { useWatchlist } from '@/lib/watchlist'
import { clsx } from 'clsx'

const ROUTES: { to: string; label: string; key: 'radar' | 'catalog' | 'watchlist' | 'airports' | 'stats' | 'feeds' | 'alerts' | 'cfg' }[] = [
  { to: '/', label: 'RADAR', key: 'radar' },
  { to: '/catalog', label: 'CATALOG', key: 'catalog' },
  { to: '/watchlist', label: 'WATCHLIST', key: 'watchlist' },
  { to: '/airports', label: 'AIRPORTS', key: 'airports' },
  { to: '/stats', label: 'STATS', key: 'stats' },
  { to: '/feeds', label: 'FEEDS', key: 'feeds' },
  { to: '/alerts', label: 'ALERTS', key: 'alerts' },
  { to: '/settings', label: 'CFG', key: 'cfg' },
]

export function TopBar({
  connState,
  stationName,
}: {
  connState: string
  stationName: string
}): React.ReactElement {
  const total = useAircraft((s) => Object.keys(s.byHex).length)
  const alerts = useAlerts((s) => s.active.size)
  const max = useStats((s) => s.current?.max_range_nm_today ?? 0)

  // Watchlist live-count badge: how many hex-kind watchlist entries are
  // currently in range. Uses the existing watchlist query (TanStack Query
  // cache) + an indexed lookup over the live aircraft registry.
  const watchlistData = useWatchlist().data
  const watchlistHexes = useMemo(() => {
    const out = new Set<string>()
    for (const e of watchlistData?.entries ?? []) {
      if (e.kind === 'hex') out.add(e.value.toLowerCase())
    }
    return out
  }, [watchlistData])
  const liveWatchlistCount = useAircraft((s) => {
    if (watchlistHexes.size === 0) return 0
    let n = 0
    for (const h of Object.keys(s.byHex)) {
      if (watchlistHexes.has(h)) n++
    }
    return n
  })

  return (
    <header
      className="flex items-center justify-between border-b border-stroke-hair bg-bg-1 font-mono text-[11px] tracking-wider"
      style={{ height: 'var(--topbar-h)' }}
    >
      {/* Left: station + clock. Hidden below lg to match the Dashboard layout breakpoint
          and to keep the tab row from overflowing on landscape phones (~844px wide). */}
      <div className="hidden lg:flex items-center gap-3 px-4 h-full shrink-0">
        <span className="text-efis-cyan uppercase">ADSB</span>
        <span className="text-text-low">·</span>
        <span className="uppercase">{stationName}</span>
        <span className="text-text-low">·</span>
        <UTCClock />
      </div>

      {/* Tabs — horizontally scrollable below lg (7 tabs won't fit in portrait phone or
          even landscape phone alongside the right-side counters). */}
      <nav className="flex items-center h-full flex-1 lg:flex-none overflow-x-auto no-scrollbar">
        {ROUTES.map((r) => (
          <NavLink
            key={r.to}
            to={r.to}
            end={r.to === '/'}
            className={({ isActive }) =>
              clsx(
                'h-full px-3 flex items-center gap-1.5 uppercase tracking-wider text-[11px] border-b-2 shrink-0',
                isActive
                  ? 'text-efis-cyan border-efis-cyan bg-bg-0'
                  : 'text-text-mid border-transparent hover:text-text-hi',
              )
            }
          >
            {r.label}
            {r.key === 'watchlist' && liveWatchlistCount > 0 && (
              <span
                className="font-mono text-[9px] px-1.5 py-0.5 bg-efis-amber/20 border border-efis-amber text-efis-amber rounded-sm"
                title={`${liveWatchlistCount} watchlist aircraft currently in range`}
              >
                {liveWatchlistCount} LIVE
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Right: live counters + connection badge. Compact layout on mobile. */}
      <div className="flex items-center gap-2 lg:gap-3 px-3 lg:px-4 h-full shrink-0">
        <span>
          <span className="text-text-low hidden sm:inline">A/C </span>
          <span className="text-efis-white">{total}</span>
        </span>
        <span className="hidden sm:inline">
          <span className="text-text-low">MAX </span>
          <span>{max.toFixed(0)}nm</span>
        </span>
        {alerts > 0 && (
          <span className="text-efis-red animate-pulse">
            {alerts}
            <span className="hidden sm:inline"> ALERT{alerts === 1 ? '' : 'S'}</span>
          </span>
        )}
        <ConnBadge state={connState} />
      </div>
    </header>
  )
}

function UTCClock(): React.ReactElement {
  const [now, setNow] = useState<string>(getUtc())
  useEffect(() => {
    const t = setInterval(() => setNow(getUtc()), 1000)
    return () => clearInterval(t)
  }, [])
  return <span className="text-efis-amber">{now}</span>
}

function getUtc(): string {
  const d = new Date()
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}Z`
}

function ConnBadge({ state }: { state: string }): React.ReactElement {
  const color =
    state === 'open'
      ? 'text-phos-hi'
      : state === 'connecting' || state === 'reconnecting'
        ? 'text-efis-amber'
        : 'text-efis-red'
  const label =
    state === 'open' ? 'LINK' : state === 'connecting' ? 'CONN' : state === 'reconnecting' ? 'RETRY' : 'DOWN'
  return (
    <span className={clsx('uppercase tracking-wider text-[10px]', color)}>
      ● <span className="hidden sm:inline">{label}</span>
    </span>
  )
}

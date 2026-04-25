import { useEffect, useState } from 'react'
import { NavLink } from 'react-router'
import { useAircraft } from '@/store/aircraft'
import { useAlerts } from '@/store/alerts'
import { useStats } from '@/store/stats'
import { clsx } from 'clsx'

const ROUTES: { to: string; label: string }[] = [
  { to: '/', label: 'RADAR' },
  { to: '/catalog', label: 'CATALOG' },
  { to: '/watchlist', label: 'WATCHLIST' },
  { to: '/stats', label: 'STATS' },
  { to: '/feeds', label: 'FEEDS' },
  { to: '/alerts', label: 'ALERTS' },
  { to: '/settings', label: 'CFG' },
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
                'h-full px-3 flex items-center uppercase tracking-wider text-[11px] border-b-2 shrink-0',
                isActive
                  ? 'text-efis-cyan border-efis-cyan bg-bg-0'
                  : 'text-text-mid border-transparent hover:text-text-hi',
              )
            }
          >
            {r.label}
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

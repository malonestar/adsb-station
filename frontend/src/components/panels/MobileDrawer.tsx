import { AnimatePresence, motion } from 'framer-motion'
import { useStats } from '@/store/stats'
import { LiveStats } from './LiveStats'
import { ClosestApproach } from './ClosestApproach'
import { LiveAlerts } from './LiveAlerts'
import { FeedHealth } from './FeedHealth'

/**
 * Collapsible bottom-sheet drawer for portrait-phone layouts.
 *
 * Collapsed: a 48px sticky bar at the bottom showing status + aircraft count.
 * Expanded: slides up to 75vh; underlying map stays visible in the top ~25vh
 * so the user can tap the map to dismiss and retains spatial context.
 *
 * Controlled component — parent (Dashboard) owns the open/close state so it
 * can coordinate with other map overlays (e.g., hiding the RadarMap's right-
 * side zoom controls while the drawer is expanded).
 */
export function MobileDrawer({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}): React.ReactElement {
  const aircraftTotal = useStats((s) => s.current?.aircraft_total ?? 0)

  return (
    <>
      {/* Backdrop — only rendered when expanded. Tapping it collapses. */}
      <AnimatePresence>
        {open && (
          <motion.button
            type="button"
            aria-label="Collapse live data drawer"
            onClick={() => onOpenChange(false)}
            className="fixed inset-0 z-[14] bg-transparent cursor-default"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
        )}
      </AnimatePresence>

      {/* Drawer itself — pinned to VIEWPORT bottom via fixed positioning so
          layout quirks in the map section can't hide it. Collapsed = 48px,
          expanded = 75vh. */}
      <motion.div
        className="
          fixed inset-x-0 bottom-0 z-[15]
          bg-bg-0 border-t border-stroke-hair
          flex flex-col overflow-hidden
        "
        initial={false}
        animate={{ height: open ? '75dvh' : 56 }}
        transition={{ type: 'spring', damping: 28, stiffness: 260 }}
        style={{
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        <HandleRow open={open} aircraftTotal={aircraftTotal} onToggle={() => onOpenChange(!open)} />
        {/* Content area — only relevant when expanded; scrolls internally. */}
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3 min-h-0">
          <LiveStats />
          <ClosestApproach />
          <LiveAlerts />
          <FeedHealth />
        </div>
      </motion.div>
    </>
  )
}

function HandleRow({
  open,
  aircraftTotal,
  onToggle,
}: {
  open: boolean
  aircraftTotal: number
  onToggle: () => void
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-label={open ? 'Collapse live data' : 'Expand live data'}
      className="
        h-14 shrink-0 flex items-center justify-between gap-3
        pl-4 pr-6 pb-2 border-b border-stroke-hair
        bg-bg-0 hover:bg-bg-1 active:bg-bg-1
        text-left
      "
    >
      <span className="flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-phos-mid animate-pulse" />
        <span className="section-header text-text-hi">LIVE DATA</span>
      </span>
      <span className="font-mono text-[11px] text-text-low">
        {aircraftTotal.toLocaleString()} {aircraftTotal === 1 ? 'aircraft' : 'aircraft'}
      </span>
      <span
        className={`font-mono text-base text-text-mid transition-transform ${
          open ? 'rotate-180' : ''
        }`}
        aria-hidden="true"
      >
        ⌃
      </span>
    </button>
  )
}

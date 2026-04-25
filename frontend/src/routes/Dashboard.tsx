import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { api } from '@/lib/api'
import { RadarMap } from '@/components/map/RadarMap'
import { LiveStats } from '@/components/panels/LiveStats'
import { FeedHealth } from '@/components/panels/FeedHealth'
import { ClosestApproach } from '@/components/panels/ClosestApproach'
import { LiveAlerts } from '@/components/panels/LiveAlerts'
import { AircraftDetail } from '@/components/panels/AircraftDetail'
import { MobileDrawer } from '@/components/panels/MobileDrawer'
import { useSelection } from '@/store/selection'

export function Dashboard(): React.ReactElement {
  const { data: receiver } = useQuery({
    queryKey: ['receiver'],
    queryFn: () => api.receiver(),
    staleTime: 60_000,
  })
  const selected = useSelection((s) => s.selectedHex)

  // MobileDrawer open/close state lives here so RadarMap can hide its right-
  // side zoom controls while the drawer is expanded (the drawer covers them).
  const [drawerOpen, setDrawerOpen] = useState(false)

  const station = { lat: receiver?.lat ?? 39.7, lon: receiver?.lon ?? -104.8 }

  return (
    <div
      // Three layout modes:
      //   - Portrait phone (< lg, portrait):  vertical stack — map (55vh) + panels below
      //   - Landscape phone (< lg, landscape): horizontal split — map fills height, panels
      //     in a ~280px right sidebar (map getting crushed vertically by a bottom panel
      //     in landscape was the phone-specific pain point)
      //   - Desktop (lg+): 3-col grid (280 | 1fr | 360)
      //
      // Detail panel becomes a fullscreen overlay on mobile (see final <aside> block).
      className="h-full flex flex-col max-lg:landscape:flex-row lg:grid lg:grid-cols-[280px_1fr_360px]"
    >
      {/* Left rail — stats + feeds + closest + alerts.
          Portrait mobile: stacked below map (order-2), grows to fill remaining height.
          Landscape mobile: fixed 280px sidebar on the right (order still 2 → after map).
          Desktop: first grid cell on the left. */}
      <aside
        className="
          order-2 lg:order-none
          max-lg:portrait:hidden
          border-t lg:border-t-0 lg:border-r
          max-lg:landscape:border-t-0 max-lg:landscape:border-l
          max-lg:landscape:w-[260px] max-lg:landscape:shrink-0
          border-stroke-hair bg-bg-0 overflow-y-auto p-3 flex flex-col gap-3
          flex-1 lg:flex-none max-lg:landscape:flex-none min-h-0
        "
      >
        <LiveStats />
        <ClosestApproach />
        <LiveAlerts />
        <FeedHealth />
      </aside>

      {/* Map — fills the remaining space in every mode. */}
      <section
        className="
          order-1 lg:order-none relative bg-bg-0 shrink-0
          h-full max-lg:landscape:h-full max-lg:landscape:flex-1 lg:h-full
        "
      >
        <RadarMap station={station} hideRightControls={drawerOpen} />
        {/* Mobile-portrait collapsible drawer (hidden via CSS on lg+ and landscape). */}
        <div className="lg:hidden max-lg:landscape:hidden">
          <MobileDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />
        </div>
      </section>

      {/* Detail / empty-state panel.
          Desktop: always rendered as the right column (3rd grid cell).
          Mobile: hidden when nothing selected; fullscreen overlay when selected.
          Safe-area insets are applied via inline style so the iOS status bar (time/
          battery) and home indicator don't occlude the close button + action row
          when the overlay is active. env() resolves to 0 on desktop, so the same
          padding is a no-op there. */}
      <aside
        className={clsx(
          'bg-bg-0 overflow-hidden',
          'lg:static lg:block lg:z-auto lg:border-l lg:border-stroke-hair',
          selected ? 'fixed inset-0 z-30' : 'hidden lg:block',
        )}
        style={
          selected
            ? {
                paddingTop: 'env(safe-area-inset-top)',
                paddingBottom: 'env(safe-area-inset-bottom)',
                paddingLeft: 'env(safe-area-inset-left)',
                paddingRight: 'env(safe-area-inset-right)',
              }
            : undefined
        }
      >
        {selected ? (
          <AircraftDetail />
        ) : (
          <div className="h-full flex items-center justify-center p-6 text-center">
            <div className="space-y-3">
              <div className="section-header text-text-low">NO SELECTION</div>
              <div className="font-mono text-[11px] text-text-mid">
                Tap any aircraft on the map to view details.
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}

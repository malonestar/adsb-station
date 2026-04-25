import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { RadarMap } from '@/components/map/RadarMap'
import { LiveStats } from '@/components/panels/LiveStats'
import { FeedHealth } from '@/components/panels/FeedHealth'
import { ClosestApproach } from '@/components/panels/ClosestApproach'
import { LiveAlerts } from '@/components/panels/LiveAlerts'
import { AircraftDetail } from '@/components/panels/AircraftDetail'
import { useSelection } from '@/store/selection'

export function Dashboard(): React.ReactElement {
  const { data: receiver } = useQuery({
    queryKey: ['receiver'],
    queryFn: () => api.receiver(),
    staleTime: 60_000,
  })
  const selected = useSelection((s) => s.selectedHex)

  const station = { lat: receiver?.lat ?? 39.7, lon: receiver?.lon ?? -104.8 }

  return (
    <div className="h-full grid" style={{ gridTemplateColumns: '280px 1fr 360px' }}>
      {/* LEFT RAIL */}
      <aside className="border-r border-stroke-hair bg-bg-0 overflow-y-auto p-3 flex flex-col gap-3">
        <LiveStats />
        <FeedHealth />
        <ClosestApproach />
        <LiveAlerts />
      </aside>

      {/* MAP */}
      <section className="relative bg-bg-0">
        <RadarMap station={station} />
      </section>

      {/* RIGHT RAIL */}
      <aside className="border-l border-stroke-hair bg-bg-0 overflow-hidden">
        {selected ? (
          <AircraftDetail />
        ) : (
          <div className="h-full flex items-center justify-center p-6 text-center">
            <div className="space-y-3">
              <div className="section-header text-text-low">NO SELECTION</div>
              <div className="font-mono text-[11px] text-text-mid">
                Click any aircraft on the map to view details.
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}

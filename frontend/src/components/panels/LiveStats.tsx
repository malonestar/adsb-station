import { Panel } from '@/components/chrome/Panel'
import { DataCell } from '@/components/chrome/DataCell'
import { Sparkline } from '@/components/misc/Sparkline'
import { useStats } from '@/store/stats'
import { useAircraft } from '@/store/aircraft'
import type { SignalBucket } from '@/types/api'

export function LiveStats(): React.ReactElement {
  const stats = useStats((s) => s.current)
  const history = useStats((s) => s.msgsPerSecHistory)
  const total = useAircraft((s) => Object.keys(s.byHex).length)
  const withPos = useAircraft(
    (s) => Object.values(s.byHex).filter((a) => a.lat != null && a.lon != null).length,
  )

  const msgs = stats?.messages_per_sec ?? 0
  const max = stats?.max_range_nm_today ?? 0
  const hist = stats?.signal_histogram ?? []

  return (
    <Panel title="LIVE">
      <div className="grid grid-cols-2 gap-3 mb-3">
        <DataCell label="A/C TOTAL" value={total} accent="cyan" />
        <DataCell label="WITH POS" value={withPos} />
        <DataCell label="MSGS/SEC" value={msgs.toFixed(1)} accent="phos" />
        <DataCell label="MAX NM TODAY" value={max.toFixed(0)} unit="nm" />
      </div>

      <div className="mb-3">
        <div className="section-header mb-1">MSGS/SEC · 5 MIN</div>
        <Sparkline points={history} height={36} />
      </div>

      <SignalHistogram buckets={hist} />
    </Panel>
  )
}

function SignalHistogram({ buckets }: { buckets: SignalBucket[] }): React.ReactElement {
  if (!buckets.length) {
    return <div className="section-header">SIGNAL — NO DATA</div>
  }
  const max = Math.max(1, ...buckets.map((b) => b.count))
  return (
    <div>
      <div className="section-header mb-1">SIGNAL (dBFS)</div>
      <div className="flex items-end gap-[2px] h-12">
        {buckets.map((b) => {
          const h = Math.round((b.count / max) * 100)
          return (
            <div
              key={b.bucket}
              className="flex-1 bg-phos-dim relative"
              style={{ height: `${Math.max(1, h)}%` }}
              title={`${b.bucket} dBFS: ${b.count}`}
            >
              <div
                className="absolute inset-x-0 bottom-0 bg-phos-mid"
                style={{ height: `${Math.max(4, h)}%` }}
              />
            </div>
          )
        })}
      </div>
      <div className="flex justify-between text-text-low font-mono text-[9px] mt-1">
        <span>-40</span>
        <span>-20</span>
        <span>0</span>
      </div>
    </div>
  )
}

import { Panel } from '@/components/chrome/Panel'
import { DataCell } from '@/components/chrome/DataCell'
import { useStats } from '@/store/stats'
import { useAircraft, selectAircraftWithPosition } from '@/store/aircraft'
import { Line, LineChart, ResponsiveContainer, YAxis, Tooltip } from 'recharts'
import type { SignalBucket } from '@/types/api'

export function LiveStats(): React.ReactElement {
  const stats = useStats((s) => s.current)
  const history = useStats((s) => s.msgsPerSecHistory)
  const total = useAircraft((s) => Object.keys(s.byHex).length)
  const withPos = useAircraft(selectAircraftWithPosition).length

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

      <div className="h-12 -mx-1 mb-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history.map((p) => ({ t: p.ts, v: p.v }))}>
            <YAxis hide domain={[0, 'dataMax + 20']} />
            <Tooltip
              formatter={(v: number) => [`${v.toFixed(1)} m/s`, '']}
              labelFormatter={() => ''}
              contentStyle={{
                background: 'var(--bg-2)',
                border: '1px solid var(--stroke-hair)',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 10,
              }}
            />
            <Line
              type="monotone"
              dataKey="v"
              stroke="var(--phos-mid)"
              strokeWidth={1.2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
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

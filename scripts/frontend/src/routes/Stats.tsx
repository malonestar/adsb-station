import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Panel } from '@/components/chrome/Panel'
import { DataCell } from '@/components/chrome/DataCell'
import { useStats } from '@/store/stats'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export function Stats(): React.ReactElement {
  const live = useStats((s) => s.current)
  const history = useStats((s) => s.msgsPerSecHistory)
  const { data: agg } = useQuery({
    queryKey: ['aggregates', 14],
    queryFn: () => api.statsAggregates(14),
    staleTime: 60_000,
  })

  const daily = agg?.rows?.slice().reverse() ?? []

  return (
    <div className="h-full overflow-auto p-4 grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))' }}>
      <Panel title="NOW">
        <div className="grid grid-cols-2 gap-3">
          <DataCell label="MSGS/SEC" value={(live?.messages_per_sec ?? 0).toFixed(1)} accent="phos" />
          <DataCell label="A/C" value={live?.aircraft_total ?? 0} accent="cyan" />
          <DataCell label="WITH POS" value={live?.aircraft_with_position ?? 0} />
          <DataCell label="MAX NM TODAY" value={(live?.max_range_nm_today ?? 0).toFixed(1)} />
        </div>
      </Panel>

      <Panel title="MSGS/SEC · LAST 5 MIN">
        <div className="h-40 -mx-1">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history.map((p) => ({ t: p.ts, v: p.v }))}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--stroke-hair)" />
              <XAxis dataKey="t" hide />
              <YAxis tick={{ fill: 'var(--text-low)', fontSize: 10 }} stroke="var(--stroke-hair)" />
              <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--stroke-hair)', fontSize: 11 }} />
              <Line type="monotone" dataKey="v" stroke="var(--phos-mid)" strokeWidth={1.2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="DAILY MESSAGES">
        <div className="h-48 -mx-1">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={daily.map((r) => ({ d: r.date, v: r.msgs_total }))}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--stroke-hair)" />
              <XAxis dataKey="d" tick={{ fill: 'var(--text-low)', fontSize: 10 }} stroke="var(--stroke-hair)" />
              <YAxis tick={{ fill: 'var(--text-low)', fontSize: 10 }} stroke="var(--stroke-hair)" />
              <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--stroke-hair)', fontSize: 11 }} />
              <Bar dataKey="v" fill="var(--phos-mid)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="DAILY UNIQUE A/C">
        <div className="h-48 -mx-1">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={daily.map((r) => ({ d: r.date, v: r.aircraft_unique }))}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--stroke-hair)" />
              <XAxis dataKey="d" tick={{ fill: 'var(--text-low)', fontSize: 10 }} stroke="var(--stroke-hair)" />
              <YAxis tick={{ fill: 'var(--text-low)', fontSize: 10 }} stroke="var(--stroke-hair)" />
              <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--stroke-hair)', fontSize: 11 }} />
              <Bar dataKey="v" fill="var(--efis-cyan)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </div>
  )
}

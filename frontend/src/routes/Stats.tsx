import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Panel } from '@/components/chrome/Panel'
import { DataCell } from '@/components/chrome/DataCell'
import { Sparkline } from '@/components/misc/Sparkline'
import { GrafanaEmbed } from '@/components/panels/GrafanaEmbed'
import { useStats } from '@/store/stats'
import { clsx } from 'clsx'

type Tab = 'live' | 'health'

export function Stats(): React.ReactElement {
  const [tab, setTab] = useState<Tab>('health')

  return (
    <div className="h-full flex flex-col">
      <TabBar active={tab} onChange={setTab} />
      <div className="flex-1 min-h-0">
        {tab === 'health' ? <GrafanaEmbed /> : <LiveStatsView />}
      </div>
    </div>
  )
}

function TabBar({
  active,
  onChange,
}: {
  active: Tab
  onChange: (t: Tab) => void
}): React.ReactElement {
  return (
    <div className="flex border-b border-stroke-hair bg-bg-0">
      <TabButton active={active === 'health'} onClick={() => onChange('health')}>
        RECEIVER HEALTH
      </TabButton>
      <TabButton active={active === 'live'} onClick={() => onChange('live')}>
        LIVE STATS
      </TabButton>
    </div>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'font-mono text-[12px] font-semibold tracking-wide',
        'px-4 py-3 border-b-2 -mb-px transition-colors',
        active
          ? 'border-efis-cyan text-text-hi'
          : 'border-transparent text-text-low hover:text-text-mid',
      )}
    >
      {children}
    </button>
  )
}

function LiveStatsView(): React.ReactElement {
  const live = useStats((s) => s.current)
  const history = useStats((s) => s.msgsPerSecHistory)
  const { data: agg } = useQuery({
    queryKey: ['aggregates', 14],
    queryFn: () => api.statsAggregates(14),
    staleTime: 60_000,
  })

  const daily = agg?.rows?.slice().reverse() ?? []
  const maxMsgs = Math.max(1, ...daily.map((r) => r.msgs_total))
  const maxUnique = Math.max(1, ...daily.map((r) => r.aircraft_unique))

  return (
    <div
      className="h-full overflow-auto p-4 grid gap-4"
      style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))' }}
    >
      <Panel title="NOW">
        <div className="grid grid-cols-2 gap-3">
          <DataCell label="MSGS/SEC" value={(live?.messages_per_sec ?? 0).toFixed(1)} accent="phos" />
          <DataCell label="A/C" value={live?.aircraft_total ?? 0} accent="cyan" />
          <DataCell label="WITH POS" value={live?.aircraft_with_position ?? 0} />
          <DataCell label="MAX NM TODAY" value={(live?.max_range_nm_today ?? 0).toFixed(1)} />
        </div>
      </Panel>

      <Panel title="MSGS/SEC · LAST 5 MIN">
        <Sparkline points={history} height={120} />
      </Panel>

      <Panel title="DAILY MESSAGES">
        <BarRow data={daily.map((r) => ({ label: r.date, v: r.msgs_total }))} max={maxMsgs} color="var(--phos-mid)" />
      </Panel>

      <Panel title="DAILY UNIQUE A/C">
        <BarRow data={daily.map((r) => ({ label: r.date, v: r.aircraft_unique }))} max={maxUnique} color="var(--efis-cyan)" />
      </Panel>
    </div>
  )
}

function BarRow({
  data,
  max,
  color,
}: {
  data: { label: string; v: number }[]
  max: number
  color: string
}): React.ReactElement {
  if (!data.length) return <div className="section-header">NO DATA</div>
  return (
    <div className="flex items-end gap-1 h-32">
      {data.map((d) => {
        const h = Math.round((d.v / max) * 100)
        return (
          <div
            key={d.label}
            className="flex-1 h-full relative group"
            title={`${d.label}: ${d.v.toLocaleString()}`}
          >
            <div
              className="absolute inset-x-0 bottom-0"
              style={{ height: `${Math.max(2, h)}%`, background: color }}
            />
            <span className="absolute inset-x-0 -bottom-5 text-[9px] text-text-low font-mono text-center opacity-0 group-hover:opacity-100">
              {d.label.slice(5)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

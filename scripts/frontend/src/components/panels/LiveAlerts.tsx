import { Panel } from '@/components/chrome/Panel'
import { useAlerts, selectActiveAlerts } from '@/store/alerts'
import { useAircraft } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
import { fmtAge, fmtCallsign } from '@/lib/format'
import { clsx } from 'clsx'

const KIND_LABEL: Record<string, { label: string; color: string }> = {
  military: { label: 'MIL', color: 'text-efis-amber border-efis-amber' },
  emergency: { label: 'EMG', color: 'text-efis-red border-efis-red' },
  watchlist: { label: 'WL', color: 'text-efis-cyan border-efis-cyan' },
  interesting: { label: 'INT', color: 'text-efis-violet border-efis-violet' },
}

export function LiveAlerts(): React.ReactElement {
  const active = useAlerts(selectActiveAlerts)
  const byHex = useAircraft((s) => s.byHex)
  const select = useSelection((s) => s.select)

  return (
    <Panel
      title="ALERTS"
      action={
        <span className="section-header text-[10px] text-text-mid">{active.length}</span>
      }
    >
      {!active.length && (
        <p className="section-header text-text-low">NONE ACTIVE</p>
      )}
      <ul className="flex flex-col gap-2">
        {active.slice(0, 8).map((a) => {
          const ac = byHex[a.hex]
          const kind = KIND_LABEL[a.kind] ?? { label: a.kind.toUpperCase(), color: 'text-text-hi border-text-hi' }
          return (
            <li
              key={a.id}
              className="flex items-center justify-between cursor-pointer hover:bg-bg-2 -mx-1 px-1 py-1 rounded-sm"
              onClick={() => select(a.hex)}
            >
              <span className="flex items-center gap-2">
                <span className={clsx('font-mono text-[10px] px-1.5 py-0.5 border', kind.color)}>
                  {kind.label}
                </span>
                <span className="font-mono text-sm text-efis-white">
                  {ac ? fmtCallsign(ac) : a.hex.toUpperCase()}
                </span>
              </span>
              <span className="font-mono text-[10px] text-text-low">
                {fmtAge(a.triggered_at)}
              </span>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}

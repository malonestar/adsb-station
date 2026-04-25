import { Panel } from '@/components/chrome/Panel'
import { Button } from '@/components/chrome/Button'
import { useSettings } from '@/store/settings'

export function Settings(): React.ReactElement {
  const s = useSettings()
  return (
    <div className="h-full overflow-auto p-4 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
      <Panel title="VISUAL">
        <div className="flex flex-col gap-2">
          <Toggle label="Radar sweep" on={s.sweepOn} onClick={s.toggleSweep} />
          <Toggle label="Scanlines" on={s.scanlinesOn} onClick={s.toggleScanlines} />
          <Toggle label="Icon bloom" on={s.bloomOn} onClick={s.toggleBloom} />
          <Toggle label="Range rings" on={s.rangeRingsOn} onClick={s.toggleRangeRings} />
          <Toggle label="Persistent trails" on={s.showTrails} onClick={s.toggleTrails} />
        </div>
      </Panel>
      <Panel title="UNITS">
        <div className="font-mono text-[11px] text-text-mid">
          Currently fixed at ft / kt / nm. Metric toggle planned in Phase 3.
        </div>
      </Panel>
    </div>
  )
}

function Toggle({
  label,
  on,
  onClick,
}: {
  label: string
  on: boolean
  onClick: () => void
}): React.ReactElement {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[12px] text-text-hi">{label}</span>
      <Button variant={on ? 'primary' : 'ghost'} size="sm" onClick={onClick}>
        {on ? 'ON' : 'OFF'}
      </Button>
    </div>
  )
}

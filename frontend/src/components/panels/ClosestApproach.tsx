import { useMemo } from 'react'
import { Panel } from '@/components/chrome/Panel'
import { DataCell } from '@/components/chrome/DataCell'
import { useShallow } from 'zustand/react/shallow'
import { useAircraft, selectAircraftWithPosition } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
import { fmtAltFt, fmtBearing, fmtCallsign, fmtDistanceNm, fmtSpeedKt } from '@/lib/format'

export function ClosestApproach(): React.ReactElement {
  const aircraft = useAircraft(useShallow(selectAircraftWithPosition))
  const select = useSelection((s) => s.select)

  const closest = useMemo(() => {
    return aircraft
      .filter((a) => a.distance_nm != null)
      .sort((a, b) => (a.distance_nm ?? 0) - (b.distance_nm ?? 0))
      .slice(0, 4)
  }, [aircraft])

  if (!closest.length) {
    return (
      <Panel title="CLOSEST">
        <p className="section-header text-text-low">NO AIRCRAFT</p>
      </Panel>
    )
  }

  const top = closest[0]
  return (
    <Panel title="CLOSEST">
      <div className="mb-3 cursor-pointer" onClick={() => select(top.hex)}>
        <div className="font-mono text-lg text-efis-white leading-none">{fmtCallsign(top)}</div>
        <div className="grid grid-cols-3 gap-2 mt-2">
          <DataCell label="DIST" value={fmtDistanceNm(top.distance_nm)} accent="cyan" />
          <DataCell label="ALT" value={fmtAltFt(top.alt_baro)} />
          <DataCell label="SPD" value={fmtSpeedKt(top.gs)} />
        </div>
      </div>

      <ul className="flex flex-col gap-1 pt-2 border-t border-stroke-hair">
        {closest.slice(1).map((a) => (
          <li
            key={a.hex}
            className="flex items-center justify-between font-mono text-[11px] cursor-pointer hover:text-efis-cyan"
            onClick={() => select(a.hex)}
          >
            <span>{fmtCallsign(a)}</span>
            <span className="text-text-mid">
              {fmtDistanceNm(a.distance_nm)} {fmtBearing(a.bearing_deg)}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

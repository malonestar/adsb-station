import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Panel } from '@/components/chrome/Panel'
import { Button } from '@/components/chrome/Button'
import { fmtAge } from '@/lib/format'
import { clsx } from 'clsx'
import { useState } from 'react'

export function Alerts(): React.ReactElement {
  const [kind, setKind] = useState<string | null>(null)
  const { data } = useQuery({
    queryKey: ['alerts-history'],
    queryFn: () => api.alertsHistory(200),
    refetchInterval: 15_000,
  })

  const all = data?.alerts ?? []
  const filtered = kind ? all.filter((a) => a.kind === kind) : all

  return (
    <div className="h-full overflow-auto p-4">
      <Panel
        title="ALERTS · HISTORY"
        action={
          <div className="flex gap-1 flex-wrap justify-end">
            {(['military', 'emergency', 'watchlist', 'interesting', 'high_altitude'] as const).map(
              (k) => (
                <Button
                  key={k}
                  size="sm"
                  variant={kind === k ? 'primary' : 'ghost'}
                  onClick={() => setKind(kind === k ? null : k)}
                >
                  {k === 'high_altitude' ? 'ALT' : k.toUpperCase().slice(0, 3)}
                </Button>
              ),
            )}
          </div>
        }
      >
        <table className="w-full font-mono text-[11px]">
          <thead className="text-text-low border-b border-stroke-hair">
            <tr className="text-left">
              <th className="py-2 font-normal uppercase">Kind</th>
              <th className="py-2 font-normal uppercase">Hex</th>
              <th className="py-2 font-normal uppercase">Flight</th>
              <th className="py-2 font-normal uppercase">Triggered</th>
              <th className="py-2 font-normal uppercase">Cleared</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a) => (
              <tr key={a.id} className="border-b border-stroke-hair">
                <td
                  className={clsx('py-2', {
                    'text-efis-amber': a.kind === 'military',
                    'text-efis-red': a.kind === 'emergency',
                    'text-efis-cyan': a.kind === 'watchlist',
                    'text-efis-violet': a.kind === 'interesting',
                    'text-phos-hi': a.kind === 'high_altitude',
                  })}
                >
                  {a.kind.toUpperCase()}
                </td>
                <td className="py-2 text-text-mid">{a.hex.toUpperCase()}</td>
                <td className="py-2">{(a.payload as { flight?: string } | undefined)?.flight ?? '—'}</td>
                <td className="py-2 text-text-mid">{fmtAge(a.triggered_at)}</td>
                <td className="py-2 text-text-low">{a.cleared_at ? fmtAge(a.cleared_at) : '—'}</td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={5} className="text-center py-6 text-text-low">
                  No alerts yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}

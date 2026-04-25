import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Panel } from '@/components/chrome/Panel'
import { StatusLED } from '@/components/chrome/StatusLED'
import { fmtAge } from '@/lib/format'

export function Feeds(): React.ReactElement {
  const { data } = useQuery({
    queryKey: ['feeds-health'],
    queryFn: () => api.feedsHealth(),
    refetchInterval: 10_000,
  })
  const feeds = data?.feeds ?? []

  return (
    <div className="h-full overflow-auto p-4 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
      {feeds.map((f) => (
        <Panel key={f.name} title={f.name}>
          <div className="flex items-center gap-3 mb-3">
            <StatusLED state={f.state === 'absent' ? 'absent' : f.state} showLabel size={10} />
            <div className="font-mono text-[11px] text-text-mid">
              {f.docker_status ?? '—'}
              {f.docker_health && f.docker_health !== f.docker_status && (
                <> / {f.docker_health}</>
              )}
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-2 font-mono text-[11px]">
            <dt className="text-text-low">Updated</dt>
            <dd>{fmtAge(f.updated_at)}</dd>
            <dt className="text-text-low">Started</dt>
            <dd>{f.started_at ? fmtAge(f.started_at) : '—'}</dd>
            {f.message_rate != null && (
              <>
                <dt className="text-text-low">Msgs/s</dt>
                <dd>{f.message_rate.toFixed(1)}</dd>
              </>
            )}
            {f.last_error && (
              <>
                <dt className="text-text-low">Error</dt>
                <dd className="text-efis-red break-all">{f.last_error}</dd>
              </>
            )}
          </dl>
        </Panel>
      ))}
    </div>
  )
}

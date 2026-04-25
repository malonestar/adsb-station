import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { StatusLED } from '@/components/chrome/StatusLED'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import { fmtAge } from '@/lib/format'

const FEEDER_FRIENDLY_NAMES: Record<string, string> = {
  ultrafeeder: 'Ultrafeeder — decoder + adsb.lol + adsb.fi + airplanes.live + adsbx',
  'adsb-backend': 'Dashboard API',
  piaware: 'FlightAware',
  fr24feed: 'Flightradar24',
  rbfeeder: 'AirNav Radar',
  'opensky-feeder': 'OpenSky Network',
}

const FEEDER_CATEGORY: Record<string, string> = {
  ultrafeeder: 'CORE',
  'adsb-backend': 'CORE',
  piaware: 'PREMIUM',
  rbfeeder: 'PREMIUM',
  fr24feed: 'PREMIUM',
  'opensky-feeder': 'ACADEMIC',
}

const COL_TEMPLATE = '24px 1fr 90px 160px 100px 100px 90px'

export function Feeds(): React.ReactElement {
  const { data } = useQuery({
    queryKey: ['feeds-health'],
    queryFn: () => api.feedsHealth(),
    refetchInterval: 10_000,
  })
  const feeds = data?.feeds ?? []

  return (
    <div className="h-full overflow-auto p-4">
      <div className="max-w-6xl mx-auto">
        {/* Column headers — desktop only */}
        <div
          className="hidden lg:grid gap-4 items-center px-4 py-2 border-b border-stroke-hair"
          style={{ gridTemplateColumns: COL_TEMPLATE }}
        >
          <span />
          <SectionHeader>Feeder</SectionHeader>
          <SectionHeader>Tier</SectionHeader>
          <SectionHeader>Docker</SectionHeader>
          <SectionHeader>Updated</SectionHeader>
          <SectionHeader>Started</SectionHeader>
          <SectionHeader className="justify-end">Msgs/s</SectionHeader>
        </div>

        {/* Rows */}
        <div>
          {feeds.map((f) => {
            const friendly = FEEDER_FRIENDLY_NAMES[f.name]
            const category = FEEDER_CATEGORY[f.name] ?? '—'
            const dockerText =
              (f.docker_status ?? '—') +
              (f.docker_health && f.docker_health !== f.docker_status ? ` / ${f.docker_health}` : '')
            const rate = f.message_rate != null ? f.message_rate.toFixed(1) : '—'
            return (
              <div
                key={f.name}
                className="border-b border-stroke-hair hover:bg-bg-1 transition-colors"
              >
                {/* Mobile layout (<lg) — stacked card */}
                <div className="lg:hidden px-4 py-3">
                  <div className="flex items-center gap-3">
                    <StatusLED state={f.state === 'absent' ? 'absent' : f.state} size={10} />
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-[13px] text-text-hi truncate">{f.name}</div>
                      {friendly && (
                        <div className="font-mono text-[10px] text-text-low uppercase tracking-wider mt-0.5 truncate">
                          {friendly}
                        </div>
                      )}
                    </div>
                    <div className="font-mono text-right tabular-nums shrink-0">
                      <div className="text-[14px] text-text-hi">{rate}</div>
                      <div className="text-[9px] text-text-low uppercase tracking-wider">msgs/s</div>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-text-mid">
                    <span className="uppercase tracking-wider">{category}</span>
                    <span className="truncate max-w-[60%]">{dockerText}</span>
                    <span>upd {fmtAge(f.updated_at)}</span>
                    <span>up {f.started_at ? fmtAge(f.started_at) : '—'}</span>
                  </div>
                </div>

                {/* Desktop layout (lg+) — dense table row */}
                <div
                  className="hidden lg:grid gap-4 items-center px-4 py-3"
                  style={{ gridTemplateColumns: COL_TEMPLATE }}
                >
                  <StatusLED state={f.state === 'absent' ? 'absent' : f.state} size={10} />
                  <div className="min-w-0">
                    <div className="font-mono text-[13px] text-text-hi truncate">{f.name}</div>
                    {friendly && (
                      <div className="font-mono text-[10px] text-text-low uppercase tracking-wider mt-0.5 truncate">
                        {friendly}
                      </div>
                    )}
                  </div>
                  <div className="font-mono text-[10px] text-text-mid uppercase tracking-wider">
                    {category}
                  </div>
                  <div className="font-mono text-[11px] text-text-mid truncate">
                    {f.docker_status ?? '—'}
                    {f.docker_health && f.docker_health !== f.docker_status && (
                      <span className="text-text-low"> / {f.docker_health}</span>
                    )}
                  </div>
                  <div className="font-mono text-[11px] text-text-mid">
                    {fmtAge(f.updated_at)}
                  </div>
                  <div className="font-mono text-[11px] text-text-mid">
                    {f.started_at ? fmtAge(f.started_at) : '—'}
                  </div>
                  <div className="font-mono text-[11px] text-text-hi text-right tabular-nums">
                    {rate}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Errors section — only renders if any feed has an error */}
        {feeds.some((f) => f.last_error) && (
          <div className="mt-6 space-y-2">
            <SectionHeader className="mb-2">Recent errors</SectionHeader>
            {feeds
              .filter((f) => f.last_error)
              .map((f) => (
                <div
                  key={f.name}
                  className="px-4 py-2 bg-bg-1 border border-efis-red/30 rounded-[2px]"
                >
                  <div className="font-mono text-[11px] text-efis-red mb-1">
                    {f.name}
                  </div>
                  <div className="font-mono text-[10px] text-text-mid break-all">
                    {f.last_error}
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  )
}

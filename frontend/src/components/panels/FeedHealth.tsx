import { Panel } from '@/components/chrome/Panel'
import { StatusLED } from '@/components/chrome/StatusLED'
import { useFeeds } from '@/store/feeds'
import { fmtAge } from '@/lib/format'
import { clsx } from 'clsx'

const VISIBLE_FEEDS_PRIORITY = [
  'ultrafeeder',
  'adsb-backend',
  'piaware',
  'fr24feed',
  'rbfeeder',
  'opensky-feeder',
]

export function FeedHealth(): React.ReactElement {
  const feeds = useFeeds((s) => s.entries)
  const byName = new Map(feeds.map((f) => [f.name, f]))
  const ordered = VISIBLE_FEEDS_PRIORITY.map((name) => byName.get(name) ?? { name, state: 'unknown' as const })

  const okCount = feeds.filter((f) => f.state === 'ok').length
  const total = feeds.filter((f) => f.state !== 'absent').length

  return (
    <Panel
      title="FEEDS"
      action={<span className="section-header text-[10px] text-text-mid">{okCount}/{total}</span>}
    >
      <ul className="flex flex-col gap-1">
        {ordered.map((f) => (
          <li key={f.name} className={clsx('flex items-center justify-between font-mono text-[11px]')}>
            <span className="flex items-center gap-2">
              <StatusLED state={f.state === 'absent' ? 'absent' : f.state} />
              <span className={f.state === 'absent' ? 'text-text-low' : 'text-text-hi'}>
                {f.name}
              </span>
            </span>
            <span className="text-text-low">
              {f.state === 'absent' ? '—' : fmtAge(f.updated_at ?? null)}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

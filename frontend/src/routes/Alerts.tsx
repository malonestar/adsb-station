import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { clsx } from 'clsx'
import { api } from '@/lib/api'
import { Button } from '@/components/chrome/Button'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import { useSelection } from '@/store/selection'
import { useAircraft } from '@/store/aircraft'
import { fmtAge } from '@/lib/format'
import type { Alert } from '@/types/api'

const KINDS = ['military', 'emergency', 'watchlist', 'interesting', 'high_altitude'] as const
type Kind = (typeof KINDS)[number]

const KIND_STYLE: Record<string, { label: string; tone: string; emoji: string }> = {
  military: { label: 'MILITARY', tone: 'text-efis-amber border-efis-amber bg-efis-amber/10', emoji: '🎖️' },
  emergency: { label: 'EMERGENCY', tone: 'text-efis-red border-efis-red bg-efis-red/10 animate-pulse', emoji: '🆘' },
  watchlist: { label: 'WATCHLIST', tone: 'text-efis-cyan border-efis-cyan bg-efis-cyan/10', emoji: '👀' },
  interesting: { label: 'INTERESTING', tone: 'text-efis-violet border-efis-violet bg-efis-violet/10', emoji: '✨' },
  high_altitude: { label: 'HIGH ALT', tone: 'text-phos-hi border-phos-hi bg-phos-hi/10', emoji: '🚀' },
}

export function Alerts(): React.ReactElement {
  const [kind, setKind] = useState<Kind | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['alerts-history'],
    queryFn: () => api.alertsHistory(200),
    refetchInterval: 15_000,
  })

  const all = data?.alerts ?? []
  const filtered = kind ? all.filter((a) => a.kind === kind) : all
  const counts = KINDS.reduce<Record<string, number>>(
    (acc, k) => ({ ...acc, [k]: all.filter((a) => a.kind === k).length }),
    {},
  )

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <SectionHeader>
          RECENT CATCHES{' '}
          <span className="text-text-mid">({filtered.length})</span>
        </SectionHeader>
        <div className="flex gap-1 flex-wrap">
          <Button
            size="sm"
            variant={kind === null ? 'primary' : 'ghost'}
            onClick={() => setKind(null)}
          >
            ALL ({all.length})
          </Button>
          {KINDS.map((k) => (
            <Button
              key={k}
              size="sm"
              variant={kind === k ? 'primary' : 'ghost'}
              onClick={() => setKind(kind === k ? null : k)}
              disabled={!counts[k]}
            >
              {KIND_STYLE[k].label} ({counts[k] ?? 0})
            </Button>
          ))}
        </div>
      </div>

      {isLoading && <div className="text-text-mid font-mono text-sm">Loading…</div>}
      {!isLoading && filtered.length === 0 && (
        <div className="text-text-low font-mono text-sm py-12 text-center">
          {kind ? `No ${KIND_STYLE[kind].label.toLowerCase()} alerts.` : 'No alerts yet.'}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((a) => (
          <AlertCard key={a.id} alert={a} />
        ))}
      </div>
    </div>
  )
}

function AlertCard({ alert: a }: { alert: Alert }): React.ReactElement {
  const navigate = useNavigate()
  const select = useSelection((s) => s.select)
  const isLive = useAircraft((s) => Boolean(s.byHex[a.hex.toLowerCase()]))
  const style = KIND_STYLE[a.kind] ?? KIND_STYLE.interesting

  const payload = a.payload as {
    flight?: string
    alt_baro?: number | null
    peak_alt_ft?: number | null
    distance_nm?: number | null
    squawk?: string | null
    renotify?: boolean
    previous_alt_ft?: number | null
  }
  const cat = a.catalog
  const flight = payload.flight ?? cat?.registration ?? a.hex.toUpperCase()
  const reg = cat?.registration
  const type = cat?.type_code
  const operator = cat?.operator

  const onClick = () => {
    select(a.hex.toLowerCase(), { focus: isLive })
    navigate('/')
  }

  // Build the "what triggered this" detail line
  const detailBits: string[] = []
  if (a.kind === 'high_altitude') {
    if (payload.peak_alt_ft && payload.peak_alt_ft !== payload.alt_baro) {
      detailBits.push(`peak FL${Math.round(payload.peak_alt_ft / 100)}`)
    } else if (payload.alt_baro) {
      detailBits.push(`crossed at ${payload.alt_baro.toLocaleString()} ft`)
    }
  } else if (payload.alt_baro) {
    detailBits.push(`${payload.alt_baro.toLocaleString()} ft`)
  }
  if (payload.distance_nm != null) {
    detailBits.push(`${payload.distance_nm.toFixed(1)} nm`)
  }
  if (payload.squawk) {
    detailBits.push(`SQ ${payload.squawk}`)
  }

  return (
    <div
      onClick={onClick}
      className={clsx(
        'flex border border-stroke-hair bg-panel-bg cursor-pointer overflow-hidden',
        'hover:border-efis-cyan transition-colors',
        a.cleared_at == null && 'border-l-2 border-l-efis-phos',
      )}
      title="Click to view on radar"
    >
      {/* Photo */}
      <div className="w-24 h-20 sm:w-32 sm:h-24 shrink-0 bg-stroke-hair/30 flex items-center justify-center">
        {cat?.photo_url ? (
          <img
            src={cat.photo_thumb_url ?? cat.photo_url}
            alt={a.hex}
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-text-low font-mono text-[10px]">no photo</span>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 p-3 flex flex-col gap-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={clsx(
              'font-mono text-[10px] px-2 py-0.5 border tabular-nums',
              style.tone,
            )}
          >
            {style.emoji} {style.label}
          </span>
          {a.cleared_at == null && (
            <span className="font-mono text-[10px] text-efis-phos flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-efis-phos animate-pulse" />
              ACTIVE
            </span>
          )}
          {isLive && (
            <span className="font-mono text-[10px] text-efis-cyan">IN RANGE</span>
          )}
          {payload.renotify && (
            <span className="font-mono text-[10px] text-text-mid italic">climb update</span>
          )}
          <span className="font-mono text-[10px] text-text-low ml-auto shrink-0 tabular-nums">
            {fmtAge(a.triggered_at)}
          </span>
        </div>

        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-mono text-base text-efis-white truncate">{flight}</span>
          {(reg || type) && (
            <span className="font-mono text-[11px] text-text-mid">
              {[reg, type].filter(Boolean).join(' · ')}
            </span>
          )}
          <span className="font-mono text-[10px] text-text-low ml-auto shrink-0">
            {a.hex.toUpperCase()}
          </span>
        </div>

        {operator && (
          <div className="font-mono text-[11px] text-text-mid truncate">{operator}</div>
        )}

        {detailBits.length > 0 && (
          <div className="font-mono text-[11px] text-text-low tabular-nums">
            {detailBits.join(' · ')}
          </div>
        )}
      </div>
    </div>
  )
}

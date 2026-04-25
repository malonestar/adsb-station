import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { clsx } from 'clsx'
import { api } from '@/lib/api'
import { useWatchlistMutations } from '@/lib/watchlist'
import { fmtAge, fmtAltRaw, fmtDistanceNm } from '@/lib/format'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import { Button } from '@/components/chrome/Button'
import { PhotoLightbox } from '@/components/chrome/PhotoLightbox'
import { useSelection } from '@/store/selection'
import type { WatchlistDetailItem } from '@/types/api'

type Kind = 'hex' | 'reg' | 'type' | 'operator'
type SortKey = 'value' | 'last_seen' | 'notify' | 'live'

const KIND_LABEL: Record<Kind, string> = {
  hex: 'HEX',
  reg: 'REG',
  type: 'TYPE',
  operator: 'OPERATOR',
}

const HEX_RE = /^[0-9a-fA-F]{6}$/

export function Watchlist(): React.ReactElement {
  const { data, isLoading } = useQuery({
    queryKey: ['watchlist-details'],
    queryFn: () => api.watchlistDetails(),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })

  const items = data?.items ?? []
  const [search, setSearch] = useState('')
  const [kindFilter, setKindFilter] = useState<Kind | null>(null)
  const [sort, setSort] = useState<SortKey>('live')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const liveCount = items.filter((i) => i.live).length
  const notifyingCount = items.filter((i) => i.notify).length
  const passiveCount = items.length - notifyingCount

  // Filter pipeline: kind chip → search → sort
  const filtered = useMemo(() => {
    const lower = search.trim().toLowerCase()
    let out = items
    if (kindFilter) out = out.filter((i) => i.kind === kindFilter)
    if (lower) {
      out = out.filter((i) => {
        if (i.value.toLowerCase().includes(lower)) return true
        if (i.label?.toLowerCase().includes(lower)) return true
        const c = i.catalog
        if (c?.registration?.toLowerCase().includes(lower)) return true
        if (c?.type_code?.toLowerCase().includes(lower)) return true
        if (c?.operator?.toLowerCase().includes(lower)) return true
        return false
      })
    }
    out = [...out].sort((a, b) => sortItems(a, b, sort, sortDir))
    return out
  }, [items, kindFilter, search, sort, sortDir])

  const onSort = (col: SortKey) => {
    if (sort === col) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    else {
      setSort(col)
      setSortDir(col === 'value' ? 'asc' : 'desc')
    }
  }

  const [addOpen, setAddOpen] = useState(false)
  const [lightboxItem, setLightboxItem] = useState<WatchlistDetailItem | null>(null)

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      {/* Header — title + summary + search + ADD */}
      <div className="flex flex-wrap items-center gap-3">
        <SectionHeader>
          WATCHLIST{' '}
          <span className="text-text-mid font-mono text-[11px]">
            {items.length} entries · {notifyingCount} notifying · {passiveCount} passive · {liveCount} live
          </span>
        </SectionHeader>
        <div className="flex-1 min-w-[200px]">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="search hex, reg, type, operator, label…"
            className="w-full bg-bg-2 border border-stroke-hair px-3 py-1.5 font-mono text-xs text-text-hi placeholder:text-text-low focus:outline-none focus:border-efis-cyan"
          />
        </div>
        <Button variant="primary" onClick={() => setAddOpen(true)} className="px-3 py-1.5 text-xs shrink-0">
          + ADD
        </Button>
      </div>

      {/* Kind filter chips */}
      <div className="flex flex-wrap gap-2">
        <Chip active={kindFilter === null} onClick={() => setKindFilter(null)}>
          ALL ({items.length})
        </Chip>
        {(['hex', 'reg', 'type', 'operator'] as Kind[]).map((k) => {
          const count = items.filter((i) => i.kind === k).length
          return (
            <Chip
              key={k}
              active={kindFilter === k}
              onClick={() => setKindFilter(kindFilter === k ? null : k)}
              disabled={count === 0}
            >
              {KIND_LABEL[k]} ({count})
            </Chip>
          )
        })}
      </div>

      {isLoading && <div className="text-text-mid font-mono text-sm">Loading…</div>}
      {!isLoading && filtered.length === 0 && (
        <div className="text-text-low font-mono text-sm py-12 text-center">
          {items.length === 0
            ? 'No watchlist entries yet. Click + ADD or use the WATCH button on any aircraft.'
            : 'No entries match the current filter.'}
        </div>
      )}

      {/* Desktop table (lg+) */}
      {filtered.length > 0 && (
        <div className="hidden lg:block bg-bg-1 border border-stroke-hair">
          {/* Header row */}
          <div
            className="grid gap-3 items-center px-3 py-2 border-b border-stroke-hair font-mono text-[10px] text-text-low uppercase tracking-wider"
            style={{ gridTemplateColumns: TABLE_COLS }}
          >
            <span>Live</span>
            <span>Photo</span>
            <SortHeader col="value" label="Identifier" sort={sort} dir={sortDir} onSort={onSort} />
            <span>Type / Operator</span>
            <span>Label</span>
            <SortHeader col="last_seen" label="Last seen" sort={sort} dir={sortDir} onSort={onSort} numeric />
            <SortHeader col="notify" label="Notify" sort={sort} dir={sortDir} onSort={onSort} />
            <span />
          </div>
          <div>
            {filtered.map((it) => (
              <WatchRow key={it.id} item={it} onClickPhoto={() => setLightboxItem(it)} />
            ))}
          </div>
        </div>
      )}

      {/* Mobile cards (below lg) */}
      {filtered.length > 0 && (
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:hidden">
          {filtered.map((it) => (
            <WatchCard key={it.id} item={it} onClickPhoto={() => setLightboxItem(it)} />
          ))}
        </div>
      )}

      {addOpen && <AddEntryModal onClose={() => setAddOpen(false)} />}
      {lightboxItem?.catalog?.photo_url && (
        <PhotoLightbox
          imageUrl={lightboxItem.catalog.photo_url}
          caption={[
            lightboxItem.catalog.registration ?? lightboxItem.value.toUpperCase(),
            lightboxItem.catalog.type_code,
            lightboxItem.catalog.operator,
          ]
            .filter(Boolean)
            .join(' · ')}
          sourceUrl={lightboxItem.catalog.photo_link}
          onClose={() => setLightboxItem(null)}
        />
      )}
    </div>
  )
}

// 8-column desktop layout: status / photo / identifier / type+op / label / last / notify / actions
const TABLE_COLS = '40px 56px minmax(140px, 1.6fr) minmax(140px, 1.4fr) minmax(120px, 1fr) 90px 100px 32px'

function sortItems(
  a: WatchlistDetailItem,
  b: WatchlistDetailItem,
  key: SortKey,
  dir: 'asc' | 'desc',
): number {
  const sign = dir === 'asc' ? 1 : -1
  switch (key) {
    case 'value':
      return sign * a.value.localeCompare(b.value)
    case 'last_seen': {
      const av = a.catalog?.last_seen ? Date.parse(a.catalog.last_seen) : 0
      const bv = b.catalog?.last_seen ? Date.parse(b.catalog.last_seen) : 0
      return sign * (av - bv)
    }
    case 'notify':
      return sign * (Number(a.notify) - Number(b.notify))
    case 'live':
      // Live first, then ever-seen by recency, then never-seen
      if (a.live !== b.live) return sign * (Number(a.live) - Number(b.live))
      return sign * (
        ((b.catalog?.last_seen ? Date.parse(b.catalog.last_seen) : 0) -
         (a.catalog?.last_seen ? Date.parse(a.catalog.last_seen) : 0))
      )
  }
}

function SortHeader({
  col,
  label,
  sort,
  dir,
  onSort,
  numeric,
}: {
  col: SortKey
  label: string
  sort: SortKey
  dir: 'asc' | 'desc'
  onSort: (c: SortKey) => void
  numeric?: boolean
}): React.ReactElement {
  const active = sort === col
  return (
    <button
      type="button"
      onClick={() => onSort(col)}
      className={clsx(
        'text-left text-[10px] uppercase tracking-wider hover:text-efis-cyan',
        active ? 'text-efis-cyan' : 'text-text-low',
        numeric && 'tabular-nums',
      )}
    >
      {label} {active ? (dir === 'desc' ? '↓' : '↑') : ''}
    </button>
  )
}

function Chip({
  children,
  active,
  onClick,
  disabled,
}: {
  children: React.ReactNode
  active: boolean
  onClick: () => void
  disabled?: boolean
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        'font-mono text-[10px] uppercase tracking-wider px-2 py-1 border',
        active
          ? 'bg-efis-cyan/20 border-efis-cyan text-efis-cyan'
          : 'border-stroke-hair text-text-mid hover:text-text-hi',
        disabled && 'opacity-40 cursor-not-allowed',
      )}
    >
      {children}
    </button>
  )
}

function NotifyToggle({ item }: { item: WatchlistDetailItem }): React.ReactElement {
  const { setNotify } = useWatchlistMutations()
  const onClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    setNotify.mutate({ id: item.id, notify: !item.notify })
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={setNotify.isPending}
      title={
        item.notify
          ? 'Notifying — click to make passive (no alerts, still on watchlist)'
          : 'Passive — click to enable Telegram/Discord notifications'
      }
      className={clsx(
        'font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 border flex items-center gap-1',
        item.notify
          ? 'bg-efis-amber/20 border-efis-amber text-efis-amber'
          : 'border-stroke-hair text-text-low hover:text-text-mid',
      )}
    >
      {item.notify ? '🔔' : '🔕'} {item.notify ? 'NOTIFY' : 'PASSIVE'}
    </button>
  )
}

function StatusPill({ item }: { item: WatchlistDetailItem }): React.ReactElement {
  if (item.live) {
    return (
      <span className="font-mono text-[10px] px-1.5 py-0.5 bg-efis-phos/20 border border-efis-phos text-efis-phos flex items-center gap-1 w-fit">
        <span className="w-1.5 h-1.5 rounded-full bg-efis-phos animate-pulse" /> LIVE
      </span>
    )
  }
  const everSeen = item.catalog ? item.catalog.seen_count > 0 : false
  if (!everSeen) {
    return (
      <span className="font-mono text-[10px] px-1.5 py-0.5 border border-stroke-hair text-text-low w-fit">
        NEVER
      </span>
    )
  }
  return (
    <span className="font-mono text-[10px] text-text-mid">
      {fmtAge(item.catalog?.last_seen ?? null)}
    </span>
  )
}

// ── Desktop table row ───────────────────────────────────────────────────

function WatchRow({
  item,
  onClickPhoto,
}: {
  item: WatchlistDetailItem
  onClickPhoto: () => void
}): React.ReactElement {
  const { remove } = useWatchlistMutations()
  const select = useSelection((s) => s.select)
  const navigate = useNavigate()
  const cat = item.catalog

  const onRemove = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm(`Remove ${KIND_LABEL[item.kind]} "${item.value.toUpperCase()}" from watchlist?`))
      remove.mutate(item.id)
  }
  const onRowClick = () => {
    if (item.kind !== 'hex') return // non-hex entries don't map to a single aircraft
    select(item.value.toLowerCase(), { focus: item.live })
    navigate('/')
  }

  return (
    <div
      onClick={onRowClick}
      className={clsx(
        'grid gap-3 items-center px-3 py-2 border-b border-stroke-hair last:border-b-0',
        item.kind === 'hex' && 'cursor-pointer hover:bg-bg-2',
      )}
      style={{ gridTemplateColumns: TABLE_COLS }}
    >
      <StatusPill item={item} />
      <div
        className={clsx(
          'h-9 w-13 bg-stroke-hair/20 flex items-center justify-center overflow-hidden',
          cat?.photo_url && 'cursor-pointer',
        )}
        onClick={(e) => {
          if (cat?.photo_url) {
            e.stopPropagation()
            onClickPhoto()
          }
        }}
        style={{ width: 56, height: 36 }}
      >
        {cat?.photo_thumb_url ? (
          <img src={cat.photo_thumb_url} alt="" className="w-full h-full object-cover" />
        ) : (
          <span className="text-text-low font-mono text-[9px]">no img</span>
        )}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-text-low uppercase">
            {KIND_LABEL[item.kind]}
          </span>
          <span className="font-mono text-[13px] text-efis-white truncate">
            {cat?.registration ?? item.value.toUpperCase()}
          </span>
        </div>
        {cat?.registration && cat.registration.toLowerCase() !== item.value.toLowerCase() && (
          <div className="font-mono text-[10px] text-text-low">{item.value.toUpperCase()}</div>
        )}
      </div>
      <div className="font-mono text-[11px] text-text-mid truncate">
        {[cat?.type_code, cat?.operator].filter(Boolean).join(' · ') || (
          <span className="text-text-low">—</span>
        )}
      </div>
      <div className="font-mono text-[11px] text-efis-cyan truncate">{item.label || ''}</div>
      <div className="font-mono text-[11px] text-text-mid tabular-nums">
        {item.live ? '—' : item.catalog?.seen_count
          ? fmtAge(item.catalog.last_seen)
          : <span className="text-text-low">never</span>}
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <NotifyToggle item={item} />
      </div>
      <button
        type="button"
        onClick={onRemove}
        title="Remove"
        aria-label="Remove"
        className="w-7 h-7 flex items-center justify-center text-text-low hover:text-efis-red"
      >
        ×
      </button>
    </div>
  )
}

// ── Mobile card ─────────────────────────────────────────────────────────

function WatchCard({
  item,
  onClickPhoto,
}: {
  item: WatchlistDetailItem
  onClickPhoto: () => void
}): React.ReactElement {
  const { remove } = useWatchlistMutations()
  const select = useSelection((s) => s.select)
  const navigate = useNavigate()
  const cat = item.catalog
  const everSeen = cat ? cat.seen_count > 0 : false
  const photo = cat?.photo_url
  const reg = cat?.registration ?? null
  const type = cat?.type_code ?? null
  const operator = cat?.operator ?? null

  const onRemove = () => {
    if (confirm(`Remove ${KIND_LABEL[item.kind]} "${item.value.toUpperCase()}" from watchlist?`))
      remove.mutate(item.id)
  }
  const onTrack = () => {
    if (item.live && item.kind === 'hex') {
      select(item.value.toLowerCase(), { focus: true })
      navigate('/')
    }
  }

  return (
    <div className="border border-stroke-hair bg-panel-bg flex flex-col">
      <div
        className={clsx(
          'aspect-[16/9] bg-stroke-hair/30 flex items-center justify-center relative overflow-hidden',
          photo && 'cursor-pointer',
        )}
        onClick={photo ? onClickPhoto : undefined}
      >
        {photo ? (
          <img src={photo} alt={item.value} className="w-full h-full object-cover" />
        ) : (
          <span className="text-text-low font-mono text-xs">no photo</span>
        )}
        <div className="absolute top-2 left-2 flex flex-wrap gap-1">
          <StatusPill item={item} />
          {cat?.is_military && (
            <span className="font-mono text-[10px] px-2 py-0.5 border border-efis-amber text-efis-amber bg-black/40">
              MIL
            </span>
          )}
          {cat?.is_interesting && !cat?.is_military && (
            <span className="font-mono text-[10px] px-2 py-0.5 border border-efis-violet text-efis-violet bg-black/40">
              INTR
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="absolute top-2 right-2 w-7 h-7 flex items-center justify-center bg-black/60 border border-stroke-hair text-text-mid hover:text-efis-red hover:border-efis-red"
          aria-label="Remove"
        >
          ×
        </button>
      </div>

      <div className="p-3 flex-1 flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-mono text-base text-efis-white truncate">
            {reg ?? item.value.toUpperCase()}
          </span>
          <span className="font-mono text-[10px] text-text-low shrink-0">
            {KIND_LABEL[item.kind]}
            {item.kind === 'hex' && ` · ${item.value.toUpperCase()}`}
          </span>
        </div>
        <div className="font-mono text-[11px] text-text-mid leading-snug">
          {[type, operator].filter(Boolean).join(' · ') || (
            <span className="text-text-low">no enrichment yet</span>
          )}
        </div>
        {item.label && (
          <div className="font-mono text-[11px] text-efis-cyan leading-snug">{item.label}</div>
        )}

        {everSeen && cat && (
          <div className="grid grid-cols-3 gap-2 pt-2 border-t border-stroke-hair text-[10px] font-mono">
            <div>
              <div className="text-text-low">SEEN</div>
              <div className="text-text-high">{cat.seen_count}</div>
            </div>
            <div>
              <div className="text-text-low">MAX ALT</div>
              <div className="text-text-high">{fmtAltRaw(cat.max_alt_ft)}</div>
            </div>
            <div>
              <div className="text-text-low">CLOSEST</div>
              <div className="text-text-high">{fmtDistanceNm(cat.min_distance_nm)}</div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-2 mt-1 pt-2 border-t border-stroke-hair">
          <NotifyToggle item={item} />
          {item.live && item.kind === 'hex' && (
            <Button variant="ghost" onClick={onTrack} className="px-2 py-1 text-[11px]">
              TRACK ↗
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── +ADD modal: kind selector + notify checkbox + volume warning ────────

function AddEntryModal({ onClose }: { onClose: () => void }): React.ReactElement {
  const { add } = useWatchlistMutations()
  const [kind, setKind] = useState<Kind>('hex')
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [notify, setNotify] = useState(true)

  // When the user changes kind, sensibly default the notify checkbox: hex on,
  // others off. They can still override before submitting.
  const onKindChange = (k: Kind) => {
    setKind(k)
    setNotify(k === 'hex')
  }

  // Per-kind validation. Hex must be 6 hex chars; others just non-empty.
  const trimmed = value.trim()
  const valid =
    kind === 'hex' ? HEX_RE.test(trimmed) : trimmed.length > 0
  const submitting = add.isPending

  const isOperatorOnly = kind === 'operator'

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid || submitting) return
    const submitValue = kind === 'hex' ? trimmed.toLowerCase() : trimmed
    add.mutate(
      {
        kind,
        value: submitValue,
        label: label.trim() || undefined,
        notify,
      },
      { onSuccess: () => onClose() },
    )
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <form
        onSubmit={onSubmit}
        onClick={(e) => e.stopPropagation()}
        className="bg-panel-bg border border-efis-cyan p-4 w-full max-w-md space-y-3"
      >
        <div className="font-mono text-sm text-efis-cyan">ADD WATCHLIST ENTRY</div>

        {/* Kind selector */}
        <div className="space-y-1">
          <label className="font-mono text-[11px] text-text-mid block">Match by</label>
          <div className="grid grid-cols-4 gap-1">
            {(['hex', 'reg', 'type', 'operator'] as Kind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => onKindChange(k)}
                className={clsx(
                  'font-mono text-[10px] uppercase tracking-wider py-1.5 border',
                  kind === k
                    ? 'bg-efis-cyan/20 border-efis-cyan text-efis-cyan'
                    : 'border-stroke-hair text-text-mid hover:text-text-hi',
                )}
              >
                {KIND_LABEL[k]}
              </button>
            ))}
          </div>
        </div>

        {/* Value input — placeholder + helper change with kind */}
        <div className="space-y-1">
          <label className="font-mono text-[11px] text-text-mid block">
            {kind === 'hex' && 'ICAO Hex (6 chars)'}
            {kind === 'reg' && 'Tail registration (e.g. N138GL)'}
            {kind === 'type' && 'ICAO type code (e.g. C17, B738)'}
            {kind === 'operator' && 'Operator (e.g. NASA, United Airlines)'}
          </label>
          <input
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={
              kind === 'hex'
                ? 'a966b2'
                : kind === 'reg'
                  ? 'N138GL'
                  : kind === 'type'
                    ? 'C17'
                    : 'NASA'
            }
            className="w-full bg-black/50 border border-stroke-hair px-2 py-1.5 font-mono text-sm text-efis-white focus:border-efis-cyan focus:outline-none"
            spellCheck={false}
          />
          {trimmed && !valid && kind === 'hex' && (
            <div className="font-mono text-[10px] text-efis-red">
              Hex must be 6 characters (0-9, a-f).
            </div>
          )}
        </div>

        {/* Label */}
        <div className="space-y-1">
          <label className="font-mono text-[11px] text-text-mid block">Label (optional)</label>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. NASA WB-57 / state aircraft"
            className="w-full bg-black/50 border border-stroke-hair px-2 py-1.5 font-mono text-sm text-efis-white focus:border-efis-cyan focus:outline-none"
          />
        </div>

        {/* Notify checkbox + warning */}
        <div className="border-t border-stroke-hair pt-3 space-y-2">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={notify}
              onChange={(e) => setNotify(e.target.checked)}
              disabled={isOperatorOnly}
              className="mt-0.5"
            />
            <div className="flex-1">
              <div className="font-mono text-[12px] text-text-hi">
                Send Telegram / Discord notifications when matched
              </div>
              <div className="font-mono text-[10px] text-text-low mt-0.5">
                {kind === 'hex' &&
                  'Each individual aircraft you add is normally worth alerting on (default ON).'}
                {kind === 'reg' &&
                  'A specific tail you want pinged on. Default off — flip on if you really want this one.'}
                {kind === 'type' && (
                  <span className="text-efis-amber">
                    ⚠ Type matches every aircraft of this model — could be many alerts/day. Default off.
                  </span>
                )}
                {kind === 'operator' && (
                  <span className="text-efis-amber">
                    ⚠ Operator matching for notifications isn'​t supported yet (V1 limitation —
                    operator data lives in the catalog, not the live state). This entry will still
                    flag matched aircraft on the watchlist tab.
                  </span>
                )}
              </div>
            </div>
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose} type="button" className="px-3 py-1.5 text-xs">
            CANCEL
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={!valid || submitting}
            className="px-3 py-1.5 text-xs"
          >
            {submitting ? 'ADDING…' : 'ADD'}
          </Button>
        </div>
        {add.isError && (
          <div className="font-mono text-[10px] text-efis-red">
            Failed to add. {String(add.error)}
          </div>
        )}
      </form>
    </div>
  )
}

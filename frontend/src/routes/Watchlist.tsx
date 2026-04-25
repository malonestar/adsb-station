import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { api } from '@/lib/api'
import { useWatchlistMutations } from '@/lib/watchlist'
import { fmtAge, fmtAltRaw, fmtDistanceNm } from '@/lib/format'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import { Button } from '@/components/chrome/Button'
import { PhotoLightbox } from '@/components/chrome/PhotoLightbox'
import { useSelection } from '@/store/selection'
import { useNavigate } from 'react-router'
import type { WatchlistDetailItem } from '@/types/api'

const HEX_RE = /^[0-9a-fA-F]{6}$/

export function Watchlist(): React.ReactElement {
  const { data, isLoading } = useQuery({
    queryKey: ['watchlist-details'],
    queryFn: () => api.watchlistDetails(),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })

  const items = data?.items ?? []
  const liveCount = items.filter((i) => i.live).length

  const [addOpen, setAddOpen] = useState(false)
  const [lightboxItem, setLightboxItem] = useState<WatchlistDetailItem | null>(null)

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      <div className="flex items-center justify-between">
        <SectionHeader>
          WATCHLIST{' '}
          <span className="text-text-mid">
            ({items.length} entries · {liveCount} LIVE)
          </span>
        </SectionHeader>
        <Button variant="primary" onClick={() => setAddOpen(true)} className="px-3 py-1.5 text-xs">
          + ADD HEX
        </Button>
      </div>

      {isLoading && <div className="text-text-mid font-mono text-sm">Loading…</div>}
      {!isLoading && items.length === 0 && (
        <div className="text-text-mid font-mono text-sm py-12 text-center">
          No watchlist entries. Add a hex above, or use the WATCH button on any aircraft's detail panel.
        </div>
      )}

      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <WatchCard
            key={item.id}
            item={item}
            onClickPhoto={() => item.catalog?.photo_url && setLightboxItem(item)}
          />
        ))}
      </div>

      {addOpen && <AddHexModal onClose={() => setAddOpen(false)} />}
      {lightboxItem && lightboxItem.catalog?.photo_url && (
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
    if (confirm(`Remove ${item.value.toUpperCase()} from watchlist?`)) {
      remove.mutate(item.id)
    }
  }

  const onTrack = () => {
    if (item.live && item.kind === 'hex') {
      select(item.value.toLowerCase(), { focus: true })
      navigate('/')
    }
  }

  return (
    <div className="border border-stroke-hair bg-panel-bg flex flex-col">
      {/* Photo / placeholder */}
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
        {/* Status pill */}
        <div className="absolute top-2 left-2 flex gap-1">
          {item.live ? (
            <span className="font-mono text-[10px] px-2 py-0.5 bg-efis-phos/30 border border-efis-phos text-efis-phos flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-efis-phos animate-pulse" /> LIVE
            </span>
          ) : !everSeen ? (
            <span className="font-mono text-[10px] px-2 py-0.5 bg-stroke-hair/40 border border-stroke-hair text-text-mid">
              NEVER SEEN
            </span>
          ) : (
            <span className="font-mono text-[10px] px-2 py-0.5 bg-stroke-hair/40 border border-stroke-hair text-text-mid">
              {fmtAge(cat?.last_seen ?? null)}
            </span>
          )}
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
          title="Remove from watchlist"
          aria-label="Remove"
        >
          ×
        </button>
      </div>

      {/* Body */}
      <div className="p-3 flex-1 flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-mono text-base text-efis-white truncate">
            {reg ?? item.value.toUpperCase()}
          </span>
          <span className="font-mono text-[10px] text-text-mid shrink-0">
            {item.value.toUpperCase()}
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

        {/* Stats — only if seen */}
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

        {item.live && (
          <Button variant="ghost" onClick={onTrack} className="mt-1 px-2 py-1 text-[11px]">
            TRACK ON RADAR
          </Button>
        )}
      </div>
    </div>
  )
}

function AddHexModal({ onClose }: { onClose: () => void }): React.ReactElement {
  const { add } = useWatchlistMutations()
  const [hex, setHex] = useState('')
  const [label, setLabel] = useState('')
  const valid = HEX_RE.test(hex.trim())
  const submitting = add.isPending

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid || submitting) return
    add.mutate(
      { kind: 'hex', value: hex.trim().toLowerCase(), label: label.trim() || undefined },
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
        <div className="font-mono text-sm text-efis-cyan">ADD AIRCRAFT TO WATCHLIST</div>
        <div className="space-y-1">
          <label className="font-mono text-[11px] text-text-mid block">ICAO Hex (6 chars)</label>
          <input
            autoFocus
            value={hex}
            onChange={(e) => setHex(e.target.value)}
            placeholder="a966b2"
            className="w-full bg-black/50 border border-stroke-hair px-2 py-1.5 font-mono text-sm text-efis-white focus:border-efis-cyan focus:outline-none"
            spellCheck={false}
          />
          {hex.trim() && !valid && (
            <div className="font-mono text-[10px] text-efis-red">
              Must be 6 hexadecimal characters (0-9, a-f).
            </div>
          )}
        </div>
        <div className="space-y-1">
          <label className="font-mono text-[11px] text-text-mid block">Label (optional)</label>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. NASA WB-57"
            className="w-full bg-black/50 border border-stroke-hair px-2 py-1.5 font-mono text-sm text-efis-white focus:border-efis-cyan focus:outline-none"
          />
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


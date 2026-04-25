import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { api } from '@/lib/api'
import { SectionHeader } from '@/components/chrome/SectionHeader'
import { Button } from '@/components/chrome/Button'
import { fmtAge, fmtAltRaw, fmtDistanceNm, fmtSpeedKt } from '@/lib/format'
import type { CatalogCategory, CatalogSort } from '@/types/api'

const LIMIT = 50

interface CategoryChip {
  key: CatalogCategory
  label: string
  tone: 'default' | 'mil' | 'alert' | 'live' | 'accent'
}

const CATEGORIES: CategoryChip[] = [
  { key: 'all', label: 'ALL', tone: 'default' },
  { key: 'seen_last_hour', label: 'LAST HOUR', tone: 'live' },
  { key: 'military', label: 'MILITARY', tone: 'mil' },
  { key: 'emergency_recent', label: 'EMERGENCY 24H', tone: 'alert' },
  { key: 'watchlist', label: 'WATCHLIST', tone: 'accent' },
  { key: 'interesting', label: 'INTERESTING', tone: 'accent' },
  { key: 'has_photo', label: 'HAS PHOTO', tone: 'default' },
]

interface SortableColumn {
  key: CatalogSort
  label: string
  numeric?: boolean
}

// Columns listed here render clickable sort headers. Order must match the <td> order below.
const SORTABLE: Record<string, SortableColumn> = {
  registration: { key: 'registration', label: 'Reg' },
  seen_count: { key: 'seen_count', label: 'Seen', numeric: true },
  max_alt_ft: { key: 'max_alt_ft', label: 'Max Alt', numeric: true },
  max_speed_kt: { key: 'max_speed_kt', label: 'Max Spd', numeric: true },
  min_distance_nm: { key: 'min_distance_nm', label: 'Closest', numeric: true },
  first_seen: { key: 'first_seen', label: 'First' },
  last_seen: { key: 'last_seen', label: 'Last' },
}

export function Catalog(): React.ReactElement {
  const [offset, setOffset] = useState(0)
  const [category, setCategory] = useState<CatalogCategory>('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<CatalogSort>('last_seen')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const { data, isFetching } = useQuery({
    queryKey: ['catalog', offset, category, search, sort, sortDir],
    queryFn: () =>
      api.catalog({
        limit: LIMIT,
        offset,
        category,
        search: search || undefined,
        sort,
        sortDir,
      }),
    placeholderData: keepPreviousData,
  })

  const total = data?.total ?? 0
  const rows = data?.rows ?? []

  // Click a header: toggle direction if same column, otherwise set column with sensible default dir.
  const onSort = (col: CatalogSort): void => {
    if (sort === col) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSort(col)
      // Text columns default to ascending; numeric/date default to descending.
      setSortDir(col === 'registration' ? 'asc' : 'desc')
    }
    setOffset(0)
  }

  return (
    <div className="h-full overflow-hidden flex flex-col p-4">
      <section className="bg-bg-1 border border-stroke-hair rounded-[2px] flex flex-col flex-1 min-h-0">
        {/* Header row */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-stroke-hair flex-shrink-0">
          <SectionHeader>CATALOG</SectionHeader>
          <span className="font-mono text-[11px] text-text-low">
            {isFetching && rows.length > 0 ? 'updating…' : `${total} aircraft`}
          </span>
        </div>

        {/* Search + category chips */}
        <div className="px-3 py-3 border-b border-stroke-hair flex-shrink-0 space-y-3">
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setOffset(0)
            }}
            placeholder="search hex, registration, type, operator…"
            className="w-full bg-bg-2 border border-stroke-hair px-3 py-2 font-mono text-sm text-text-hi placeholder:text-text-low focus:outline-none focus:border-efis-cyan"
          />
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((c) => (
              <Chip
                key={c.key}
                active={category === c.key}
                tone={c.tone}
                onClick={() => {
                  setCategory(c.key)
                  setOffset(0)
                }}
              >
                {c.label}
              </Chip>
            ))}
          </div>
        </div>

        {/* Scrollable table area — sticky thead stays visible while tbody scrolls */}
        <div className="flex-1 min-h-0 overflow-auto">
          <table className="w-full font-mono text-[11px] border-collapse">
            <thead className="sticky top-0 z-10 bg-bg-1 text-text-low">
              <tr className="border-b border-stroke-hair">
                <Th>Photo</Th>
                <Th>Hex</Th>
                <SortTh col={SORTABLE.registration} currentSort={sort} dir={sortDir} onSort={onSort} />
                <Th>Type</Th>
                <Th>Operator</Th>
                <SortTh col={SORTABLE.seen_count} currentSort={sort} dir={sortDir} onSort={onSort} />
                <SortTh col={SORTABLE.max_alt_ft} currentSort={sort} dir={sortDir} onSort={onSort} />
                <SortTh col={SORTABLE.max_speed_kt} currentSort={sort} dir={sortDir} onSort={onSort} />
                <SortTh col={SORTABLE.min_distance_nm} currentSort={sort} dir={sortDir} onSort={onSort} />
                <SortTh col={SORTABLE.last_seen} currentSort={sort} dir={sortDir} onSort={onSort} />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.hex} className="border-b border-stroke-hair hover:bg-bg-2">
                  <td className="px-3 py-2">
                    {r.photo_thumb_url ? (
                      <img src={r.photo_thumb_url} alt="" className="h-8 w-14 object-cover rounded-sm" />
                    ) : (
                      <div className="h-8 w-14 bg-bg-2 border border-stroke-hair" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-text-mid">{r.hex.toUpperCase()}</td>
                  <td className="px-3 py-2 text-efis-white">{r.registration ?? '—'}</td>
                  <td
                    className={clsx(
                      'px-3 py-2',
                      r.is_military && 'text-efis-amber',
                      r.is_interesting && !r.is_military && 'text-efis-violet',
                    )}
                  >
                    {r.type_code ?? '—'}
                    {r.is_military && <span className="ml-1 text-[9px]">MIL</span>}
                    {r.is_interesting && !r.is_military && (
                      <span className="ml-1 text-[9px]">INT</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-text-mid">{r.operator ?? '—'}</td>
                  <td className="px-3 py-2 text-text-mid tabular-nums text-right">{r.seen_count}</td>
                  <td className="px-3 py-2 text-text-mid tabular-nums text-right">
                    {r.max_alt_ft != null ? fmtAltRaw(r.max_alt_ft) : '—'}
                  </td>
                  <td className="px-3 py-2 text-text-mid tabular-nums text-right">
                    {r.max_speed_kt != null ? fmtSpeedKt(r.max_speed_kt) : '—'}
                  </td>
                  <td className="px-3 py-2 text-text-mid tabular-nums text-right">
                    {r.min_distance_nm != null ? fmtDistanceNm(r.min_distance_nm) : '—'}
                  </td>
                  <td className="px-3 py-2 text-text-low tabular-nums">{fmtAge(r.last_seen)}</td>
                </tr>
              ))}
              {!rows.length && !isFetching && (
                <tr>
                  <td colSpan={10} className="text-center py-8 text-text-low">
                    {category === 'all' && !search
                      ? 'No aircraft yet. Catalog fills as enrichment returns.'
                      : 'No matches for the current filter.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="p-3 flex items-center justify-between border-t border-stroke-hair flex-shrink-0">
          <span className="font-mono text-[11px] text-text-mid tabular-nums">
            {total === 0 ? 0 : offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            >
              ← PREV
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={offset + LIMIT >= total}
              onClick={() => setOffset(offset + LIMIT)}
            >
              NEXT →
            </Button>
          </div>
        </div>
      </section>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <th className="px-3 py-2 font-normal uppercase tracking-wider text-left whitespace-nowrap">
      {children}
    </th>
  )
}

interface SortThProps {
  col: SortableColumn
  currentSort: CatalogSort
  dir: 'asc' | 'desc'
  onSort: (col: CatalogSort) => void
}

function SortTh({ col, currentSort, dir, onSort }: SortThProps): React.ReactElement {
  const active = currentSort === col.key
  const arrow = !active ? '↕' : dir === 'desc' ? '↓' : '↑'
  return (
    <th
      className={clsx(
        'px-3 py-2 font-normal uppercase tracking-wider whitespace-nowrap cursor-pointer select-none',
        col.numeric ? 'text-right' : 'text-left',
        active ? 'text-efis-cyan' : 'hover:text-text-mid',
      )}
      onClick={() => onSort(col.key)}
      title={`Sort by ${col.label}`}
    >
      {col.label} <span className={clsx('ml-1', !active && 'text-text-low')}>{arrow}</span>
    </th>
  )
}

interface ChipProps {
  active: boolean
  tone: CategoryChip['tone']
  onClick: () => void
  children: React.ReactNode
}

function Chip({ active, tone, onClick, children }: ChipProps): React.ReactElement {
  const toneCls = {
    default: active
      ? 'bg-efis-cyan/15 border-efis-cyan text-efis-cyan'
      : 'border-stroke-hair text-text-mid hover:text-text-hi hover:border-stroke-soft',
    mil: active
      ? 'bg-efis-amber/15 border-efis-amber text-efis-amber'
      : 'border-stroke-hair text-text-mid hover:text-efis-amber hover:border-efis-amber/50',
    alert: active
      ? 'bg-efis-red/15 border-efis-red text-efis-red'
      : 'border-stroke-hair text-text-mid hover:text-efis-red hover:border-efis-red/50',
    live: active
      ? 'bg-phos-hi/15 border-phos-hi text-phos-hi'
      : 'border-stroke-hair text-text-mid hover:text-phos-hi hover:border-phos-hi/50',
    accent: active
      ? 'bg-efis-violet/15 border-efis-violet text-efis-violet'
      : 'border-stroke-hair text-text-mid hover:text-efis-violet hover:border-efis-violet/50',
  }[tone]
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'px-3 py-1 border font-mono text-[10px] uppercase tracking-wider rounded-sm transition-colors',
        toneCls,
      )}
    >
      {children}
    </button>
  )
}

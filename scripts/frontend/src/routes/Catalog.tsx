import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Panel } from '@/components/chrome/Panel'
import { Button } from '@/components/chrome/Button'
import { fmtAge } from '@/lib/format'
import { clsx } from 'clsx'

export function Catalog(): React.ReactElement {
  const [offset, setOffset] = useState(0)
  const [militaryOnly, setMilitaryOnly] = useState(false)
  const [search, setSearch] = useState('')
  const LIMIT = 50

  const { data, isFetching } = useQuery({
    queryKey: ['catalog', offset, militaryOnly, search],
    queryFn: () => api.catalog({ limit: LIMIT, offset, militaryOnly, search: search || undefined }),
    placeholderData: keepPreviousData,
  })

  const total = data?.total ?? 0
  const rows = data?.rows ?? []

  return (
    <div className="h-full overflow-hidden flex flex-col p-4 gap-3">
      <Panel title="CATALOG" padded={false}>
        <div className="p-3 flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setOffset(0)
            }}
            placeholder="search hex, reg, type, operator…"
            className="flex-1 bg-bg-2 border border-stroke-hair px-3 py-2 font-mono text-sm text-text-hi placeholder:text-text-low focus:outline-none focus:border-efis-cyan"
          />
          <Button
            variant={militaryOnly ? 'primary' : 'ghost'}
            onClick={() => {
              setMilitaryOnly(!militaryOnly)
              setOffset(0)
            }}
          >
            MIL ONLY
          </Button>
        </div>

        <div className="overflow-auto">
          <table className="w-full font-mono text-[11px]">
            <thead className="text-text-low border-y border-stroke-hair">
              <tr className="text-left">
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Photo</th>
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Hex</th>
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Reg</th>
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Type</th>
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Operator</th>
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Seen</th>
                <th className="px-3 py-2 font-normal uppercase tracking-wider">Last</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.hex} className="border-b border-stroke-hair hover:bg-bg-2">
                  <td className="px-3 py-2">
                    {r.photo_thumb_url ? (
                      <img
                        src={r.photo_thumb_url}
                        alt=""
                        className="h-8 w-14 object-cover rounded-sm"
                      />
                    ) : (
                      <div className="h-8 w-14 bg-bg-2 border border-stroke-hair" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-text-mid">{r.hex.toUpperCase()}</td>
                  <td className="px-3 py-2 text-efis-white">{r.registration ?? '—'}</td>
                  <td className={clsx('px-3 py-2', r.is_military && 'text-efis-amber')}>
                    {r.type_code ?? '—'}
                    {r.is_military && <span className="ml-1 text-[9px]">MIL</span>}
                  </td>
                  <td className="px-3 py-2 text-text-mid">{r.operator ?? '—'}</td>
                  <td className="px-3 py-2 text-text-mid">{r.seen_count}</td>
                  <td className="px-3 py-2 text-text-low">{fmtAge(r.last_seen)}</td>
                </tr>
              ))}
              {!rows.length && !isFetching && (
                <tr>
                  <td colSpan={7} className="text-center py-6 text-text-low">
                    No aircraft yet. Catalog fills as enrichment returns.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-3 flex items-center justify-between border-t border-stroke-hair">
          <span className="font-mono text-[11px] text-text-mid">
            {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
              ← PREV
            </Button>
            <Button variant="ghost" size="sm" disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}>
              NEXT →
            </Button>
          </div>
        </div>
      </Panel>
    </div>
  )
}

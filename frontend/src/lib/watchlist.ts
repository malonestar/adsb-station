import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { WatchlistEntry } from '@/types/api'

const WATCHLIST_KEY = ['watchlist'] as const

export function useWatchlist() {
  return useQuery({
    queryKey: WATCHLIST_KEY,
    queryFn: () => api.watchlistList(),
    staleTime: 30_000,
  })
}

export function useWatchlistEntryFor(hex: string | null | undefined) {
  const q = useWatchlist()
  const target = hex?.toLowerCase()
  const entry = target
    ? q.data?.entries.find((e) => e.kind === 'hex' && e.value.toLowerCase() === target)
    : undefined
  return { entry, isLoading: q.isLoading }
}

export function useWatchlistMutations() {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: WATCHLIST_KEY })
    qc.invalidateQueries({ queryKey: ['watchlist-details'] })
  }

  const add = useMutation({
    mutationFn: (entry: { kind: string; value: string; label?: string; notify?: boolean }) =>
      api.watchlistAdd(entry),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.watchlistRemove(id),
    onSuccess: invalidate,
  })

  const setNotify = useMutation({
    mutationFn: ({ id, notify }: { id: number; notify: boolean }) =>
      api.watchlistSetNotify(id, notify),
    onSuccess: invalidate,
  })

  return { add, remove, setNotify }
}

export function useToggleWatch(hex: string | null | undefined, label?: string) {
  const { entry, isLoading } = useWatchlistEntryFor(hex)
  const { add, remove } = useWatchlistMutations()
  const watching = Boolean(entry)
  const isPending = add.isPending || remove.isPending

  const toggle = () => {
    if (!hex) return
    if (entry) {
      remove.mutate(entry.id)
    } else {
      add.mutate({ kind: 'hex', value: hex.toLowerCase(), label })
    }
  }

  return { watching, toggle, isPending, isLoading, entry: entry as WatchlistEntry | undefined }
}

import type {
  AircraftLiveResponse,
  AircraftTrailsResponse,
  CatalogCategory,
  CatalogResponse,
  CatalogSort,
  FeedHealthEntry,
  LiveStats,
  ReceiverInfo,
  RouteInfo,
  WatchlistEntry,
  WatchlistDetailItem,
  Alert,
  HeatmapBin,
  ReplayPoint,
  DailyAggregateRow,
} from '@/types/api'

const BASE = '/api'

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, init)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${path}`)
  return (await r.json()) as T
}

export const api = {
  receiver: () => j<ReceiverInfo>('/receiver'),
  aircraftLive: () => j<AircraftLiveResponse>('/aircraft/live'),
  aircraftDetail: (hex: string) =>
    j<{ hex: string; live: unknown; catalog: unknown; trail: unknown[] }>(`/aircraft/${hex}`),
  aircraftTrails: (seconds = 300) =>
    j<AircraftTrailsResponse>(`/aircraft/trails?seconds=${seconds}`),
  route: (hex: string) => j<RouteInfo>(`/aircraft/${hex}/route`),

  catalog: (
    p: {
      limit?: number
      offset?: number
      search?: string
      category?: CatalogCategory
      sort?: CatalogSort
      sortDir?: 'asc' | 'desc'
    } = {},
  ) =>
    j<CatalogResponse>(
      '/catalog?' +
        new URLSearchParams({
          limit: String(p.limit ?? 100),
          offset: String(p.offset ?? 0),
          category: p.category ?? 'all',
          sort: p.sort ?? 'last_seen',
          sort_dir: p.sortDir ?? 'desc',
          ...(p.search ? { search: p.search } : {}),
        }).toString(),
    ),

  statsLive: () => j<LiveStats>('/stats/live'),
  statsAggregates: (days = 14) => j<{ rows: DailyAggregateRow[] }>(`/stats/aggregates?days=${days}`),

  heatmap: (hours = 24, grid = 0.02) =>
    j<{ grid: number; hours: number; bins: HeatmapBin[] }>(
      `/history/heatmap?hours=${hours}&grid=${grid}`,
    ),

  replay: (start: string, end: string, hex?: string) => {
    const p = new URLSearchParams({ start, end, ...(hex ? { hex } : {}) })
    return j<{ rows: ReplayPoint[] }>(`/history/replay?${p.toString()}`)
  },

  alertsLive: () => j<{ alerts: Alert[] }>('/alerts/live'),
  alertsHistory: (limit = 100) => j<{ alerts: Alert[] }>(`/alerts?limit=${limit}`),

  watchlistList: () => j<{ entries: WatchlistEntry[] }>('/watchlist'),
  watchlistDetails: () => j<{ items: WatchlistDetailItem[] }>('/watchlist/details'),
  watchlistAdd: (entry: { kind: string; value: string; label?: string; notify?: boolean }) =>
    j<WatchlistEntry>('/watchlist', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(entry),
    }),
  watchlistSetNotify: (id: number, notify: boolean) =>
    j<WatchlistEntry>(`/watchlist/${id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ notify }),
    }),
  watchlistRemove: (id: number) =>
    j<{ deleted: boolean }>(`/watchlist/${id}`, { method: 'DELETE' }),

  feedsHealth: () => j<{ feeds: FeedHealthEntry[] }>('/feeds/health'),
}

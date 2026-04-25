import type {
  AircraftLiveResponse,
  CatalogResponse,
  FeedHealthEntry,
  LiveStats,
  ReceiverInfo,
  WatchlistEntry,
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

  catalog: (p: { limit?: number; offset?: number; militaryOnly?: boolean; search?: string } = {}) =>
    j<CatalogResponse>(
      '/catalog?' +
        new URLSearchParams({
          limit: String(p.limit ?? 100),
          offset: String(p.offset ?? 0),
          military_only: String(p.militaryOnly ?? false),
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
  watchlistAdd: (entry: { kind: string; value: string; label?: string }) =>
    j<WatchlistEntry>('/watchlist', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(entry),
    }),
  watchlistRemove: (id: number) =>
    j<{ deleted: boolean }>(`/watchlist/${id}`, { method: 'DELETE' }),

  feedsHealth: () => j<{ feeds: FeedHealthEntry[] }>('/feeds/health'),
}

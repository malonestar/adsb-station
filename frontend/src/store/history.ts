import { create } from 'zustand'

export type HeatmapWindow = '1h' | '24h' | '7d' | 'all'

/** Tri-state radar band filter:
 *  - 'all'      → show every aircraft (default)
 *  - 'uat-only' → show only aircraft seen via UAT (state.uat_version truthy)
 *  - 'no-uat'   → hide UAT-tagged aircraft (1090 ADS-B / Mode S only) */
export type UatFilterMode = 'all' | 'uat-only' | 'no-uat'

interface HistoryStore {
  heatmapOn: boolean
  heatmapWindow: HeatmapWindow
  allTrailsOn: boolean
  /** Show adsb.lol "global context" aircraft beyond our antenna range as a
   *  faded overlay. Off by default — adds visual density when on. */
  globalOn: boolean
  uatFilter: UatFilterMode
  /** Hex whose full-history trail is currently rendered, or null.
   *  Only one aircraft's full history is visible at a time — selecting a new
   *  aircraft and toggling its HISTORY replaces the previous trail. */
  historyHex: string | null

  setHeatmapOn: (v: boolean) => void
  setHeatmapWindow: (w: HeatmapWindow) => void
  setAllTrailsOn: (v: boolean) => void
  setGlobalOn: (v: boolean) => void
  cycleUatFilter: () => void
  /** Toggle the full-history trail for a given hex: same hex → clear, new hex → replace. */
  toggleHistoryHex: (hex: string) => void
  clearHistoryHex: () => void
}

const _UAT_CYCLE: Record<UatFilterMode, UatFilterMode> = {
  'all': 'uat-only',
  'uat-only': 'no-uat',
  'no-uat': 'all',
}

export const useHistory = create<HistoryStore>((set) => ({
  heatmapOn: false,
  heatmapWindow: '24h',
  allTrailsOn: false,
  globalOn: false,
  uatFilter: 'all',
  historyHex: null,

  setHeatmapOn: (v) => set({ heatmapOn: v }),
  setHeatmapWindow: (w) => set({ heatmapWindow: w }),
  setAllTrailsOn: (v) => set({ allTrailsOn: v }),
  setGlobalOn: (v) => set({ globalOn: v }),
  cycleUatFilter: () => set((s) => ({ uatFilter: _UAT_CYCLE[s.uatFilter] })),
  toggleHistoryHex: (hex) =>
    set((s) => ({ historyHex: s.historyHex === hex ? null : hex })),
  clearHistoryHex: () => set({ historyHex: null }),
}))

/** Maps UI window label to hours for the /api/history/heatmap query.
 *  'all' maps to 720h = 30 days, matching the positions table retention. */
export function windowToHours(w: HeatmapWindow): number {
  switch (w) {
    case '1h':
      return 1
    case '24h':
      return 24
    case '7d':
      return 168
    case 'all':
      return 720
  }
}

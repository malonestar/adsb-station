import { create } from 'zustand'
import type { AircraftDelta, AircraftEnrichment, AircraftState } from '@/types/api'

interface AircraftStore {
  byHex: Record<string, AircraftState>
  lastUpdate: number
  setSnapshot: (aircraft: AircraftState[]) => void
  applyDelta: (d: AircraftDelta) => void
  applyEnrichment: (e: AircraftEnrichment) => void
}

export const useAircraft = create<AircraftStore>((set) => ({
  byHex: {},
  lastUpdate: 0,
  setSnapshot: (aircraft) =>
    set(() => ({
      byHex: Object.fromEntries(aircraft.map((a) => [a.hex, a])),
      lastUpdate: Date.now(),
    })),
  applyDelta: ({ added, updated, removed }) =>
    set((s) => {
      const next = { ...s.byHex }
      for (const a of added) next[a.hex] = a
      for (const a of updated) next[a.hex] = a
      for (const h of removed) delete next[h]
      return { byHex: next, lastUpdate: Date.now() }
    }),
  applyEnrichment: (e) =>
    set((s) => {
      const existing = s.byHex[e.hex]
      if (!existing) return s
      return {
        byHex: {
          ...s.byHex,
          [e.hex]: {
            ...existing,
            registration: e.registration ?? existing.registration,
            type_code: e.type_code ?? existing.type_code,
          },
        },
      }
    }),
}))

export const selectAircraftArray = (s: AircraftStore): AircraftState[] =>
  Object.values(s.byHex)

export const selectAircraftWithPosition = (s: AircraftStore): AircraftState[] =>
  Object.values(s.byHex).filter((a) => a.lat != null && a.lon != null)

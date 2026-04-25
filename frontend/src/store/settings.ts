import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  scanlinesOn: boolean
  sweepOn: boolean
  bloomOn: boolean
  rangeRingsOn: boolean
  showTrails: boolean
  trailSeconds: number
  unitsFt: boolean // true = ft/kt, false = m/km
  toggleScanlines: () => void
  toggleSweep: () => void
  toggleBloom: () => void
  toggleRangeRings: () => void
  toggleTrails: () => void
  setTrailSeconds: (s: number) => void
}

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      scanlinesOn: true,
      sweepOn: true,
      bloomOn: true,
      rangeRingsOn: true,
      showTrails: true,
      trailSeconds: 120,
      unitsFt: true,
      toggleScanlines: () => set((s) => ({ scanlinesOn: !s.scanlinesOn })),
      toggleSweep: () => set((s) => ({ sweepOn: !s.sweepOn })),
      toggleBloom: () => set((s) => ({ bloomOn: !s.bloomOn })),
      toggleRangeRings: () => set((s) => ({ rangeRingsOn: !s.rangeRingsOn })),
      toggleTrails: () => set((s) => ({ showTrails: !s.showTrails })),
      setTrailSeconds: (s) => set({ trailSeconds: s }),
    }),
    { name: 'adsb-settings' },
  ),
)

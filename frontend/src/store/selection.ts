import { create } from 'zustand'

interface SelectionStore {
  selectedHex: string | null
  followSelection: boolean
  select: (hex: string | null) => void
  toggleFollow: () => void
  clear: () => void
}

export const useSelection = create<SelectionStore>((set) => ({
  selectedHex: null,
  followSelection: false,
  select: (hex) => set({ selectedHex: hex }),
  toggleFollow: () => set((s) => ({ followSelection: !s.followSelection })),
  clear: () => set({ selectedHex: null, followSelection: false }),
}))

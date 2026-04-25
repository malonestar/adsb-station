import { create } from 'zustand'

interface SelectionStore {
  selectedHex: string | null
  followSelection: boolean
  // Set by routes that navigate INTO the dashboard (Catalog row click,
  // Watchlist TRACK button) to ask the radar to pan to the aircraft on
  // arrival. Consumed once the pan happens.
  pendingFocusHex: string | null
  select: (hex: string | null, opts?: { focus?: boolean }) => void
  consumeFocus: () => void
  toggleFollow: () => void
  clear: () => void
}

export const useSelection = create<SelectionStore>((set) => ({
  selectedHex: null,
  followSelection: false,
  pendingFocusHex: null,
  select: (hex, opts) =>
    set({
      selectedHex: hex,
      pendingFocusHex: hex && opts?.focus ? hex : null,
    }),
  consumeFocus: () => set({ pendingFocusHex: null }),
  toggleFollow: () => set((s) => ({ followSelection: !s.followSelection })),
  clear: () => set({ selectedHex: null, followSelection: false, pendingFocusHex: null }),
}))

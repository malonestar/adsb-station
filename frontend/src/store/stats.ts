import { create } from 'zustand'
import type { LiveStats } from '@/types/api'

interface StatsStore {
  current: LiveStats | null
  msgsPerSecHistory: { ts: number; v: number }[]
  apply: (t: LiveStats) => void
}

const HISTORY_SECONDS = 300

export const useStats = create<StatsStore>((set) => ({
  current: null,
  msgsPerSecHistory: [],
  apply: (t) =>
    set((s) => {
      const now = Date.now()
      const cutoff = now - HISTORY_SECONDS * 1000
      const history = [...s.msgsPerSecHistory, { ts: now, v: t.messages_per_sec }].filter(
        (p) => p.ts >= cutoff,
      )
      return { current: t, msgsPerSecHistory: history }
    }),
}))

import { create } from 'zustand'
import type { FeedHealthEntry } from '@/types/api'

interface FeedsStore {
  entries: FeedHealthEntry[]
  setAll: (feeds: FeedHealthEntry[]) => void
}

export const useFeeds = create<FeedsStore>((set) => ({
  entries: [],
  setAll: (feeds) => set({ entries: feeds }),
}))

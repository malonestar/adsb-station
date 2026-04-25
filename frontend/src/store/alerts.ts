import { create } from 'zustand'
import type { Alert } from '@/types/api'

interface AlertsStore {
  active: Map<number, Alert>
  setAll: (alerts: Alert[]) => void
  add: (a: Alert) => void
  clear: (id: number) => void
}

export const useAlerts = create<AlertsStore>((set) => ({
  active: new Map(),
  setAll: (alerts) =>
    set(() => ({ active: new Map(alerts.filter((a) => !a.cleared_at).map((a) => [a.id, a])) })),
  add: (a) =>
    set((s) => {
      const next = new Map(s.active)
      next.set(a.id, a)
      return { active: next }
    }),
  clear: (id) =>
    set((s) => {
      const next = new Map(s.active)
      next.delete(id)
      return { active: next }
    }),
}))

export const selectActiveAlerts = (s: AlertsStore): Alert[] =>
  Array.from(s.active.values()).sort(
    (a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime(),
  )

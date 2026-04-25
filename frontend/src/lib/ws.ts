import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { useAircraft } from '@/store/aircraft'
import { useAlerts } from '@/store/alerts'
import { useFeeds } from '@/store/feeds'
import { useStats } from '@/store/stats'
import type { WsMessage } from '@/types/api'

type ConnState = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting'

/** Opens a single shared WebSocket for the app lifetime. Idempotent. */
export function useAdsbSocket(): ConnState {
  const [state, setState] = useState<ConnState>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const stoppedRef = useRef(false)

  useEffect(() => {
    stoppedRef.current = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    async function bootstrap() {
      try {
        const snap = await api.aircraftLive()
        useAircraft.getState().setSnapshot(snap.aircraft)
      } catch (err) {
        console.warn('bootstrap snapshot failed', err)
      }
      try {
        const alerts = await api.alertsLive()
        useAlerts.getState().setAll(alerts.alerts)
      } catch {
        /* ignore */
      }
      try {
        const feeds = await api.feedsHealth()
        useFeeds.getState().setAll(feeds.feeds)
      } catch {
        /* ignore */
      }
    }

    function connect() {
      if (stoppedRef.current) return
      setState(attemptRef.current === 0 ? 'connecting' : 'reconnecting')
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${proto}://${location.host}/ws`
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        attemptRef.current = 0
        setState('open')
        void bootstrap()
      }

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as WsMessage
          dispatch(msg)
        } catch (err) {
          console.warn('bad ws message', err)
        }
      }

      ws.onclose = () => {
        if (stoppedRef.current) return
        setState('reconnecting')
        const attempt = ++attemptRef.current
        const delay = Math.min(30_000, 1_000 * 2 ** Math.min(attempt, 6))
        reconnectTimer = setTimeout(connect, delay)
      }
      ws.onerror = () => {
        ws.close()
      }
    }

    connect()
    return () => {
      stoppedRef.current = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      wsRef.current?.close()
      setState('closed')
    }
  }, [])

  return state
}

function dispatch(msg: WsMessage): void {
  switch (msg.type) {
    case 'aircraft.delta':
      useAircraft.getState().applyDelta(msg.data)
      return
    case 'aircraft.enriched':
      useAircraft.getState().applyEnrichment(msg.data)
      return
    case 'alert.new':
      useAlerts.getState().add(msg.data)
      return
    case 'alert.cleared':
      useAlerts.getState().clear(msg.data.id)
      return
    case 'stats.tick':
      useStats.getState().apply(msg.data)
      return
    case 'feed.status':
      useFeeds.getState().setAll(msg.data.feeds)
      return
  }
}

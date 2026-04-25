import { Outlet } from 'react-router'
import { useAdsbSocket } from '@/lib/ws'
import { TopBar } from './TopBar'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function Shell(): React.ReactElement {
  const conn = useAdsbSocket()
  const { data: receiver } = useQuery({
    queryKey: ['receiver'],
    queryFn: () => api.receiver(),
    staleTime: 60_000,
  })

  return (
    <div className="h-full flex flex-col bg-bg-0">
      <TopBar connState={conn} stationName={receiver?.name ?? 'STATION'} />
      <main className="flex-1 min-h-0">
        <Outlet />
      </main>
    </div>
  )
}

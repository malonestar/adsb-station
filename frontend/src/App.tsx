import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import { Shell } from '@/components/layout/Shell'
import { Dashboard } from '@/routes/Dashboard'
import { Catalog } from '@/routes/Catalog'
import { Watchlist } from '@/routes/Watchlist'
import { Airports } from '@/routes/Airports'
import { Replay } from '@/routes/Replay'
import { Stats } from '@/routes/Stats'
import { Feeds } from '@/routes/Feeds'
import { Alerts } from '@/routes/Alerts'
import { Settings } from '@/routes/Settings'
import { Kiosk } from '@/routes/Kiosk'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, staleTime: 15_000, retry: 2 },
  },
})

export function App(): React.ReactElement {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/kiosk" element={<Kiosk />} />
          <Route path="/" element={<Shell />}>
            <Route index element={<Dashboard />} />
            <Route path="catalog" element={<Catalog />} />
            <Route path="watchlist" element={<Watchlist />} />
            <Route path="airports" element={<Airports />} />
            <Route path="replay" element={<Replay />} />
            <Route path="stats" element={<Stats />} />
            <Route path="feeds" element={<Feeds />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

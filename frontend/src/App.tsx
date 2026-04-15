import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FlowList } from './pages/FlowList'
import { FlowBuilder } from './pages/FlowBuilder'
import { Scheduler } from './pages/Scheduler'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 2000, retry: 1 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<FlowList />} />
          <Route path="/flows/:id" element={<FlowBuilder />} />
          <Route path="/scheduler" element={<Scheduler />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

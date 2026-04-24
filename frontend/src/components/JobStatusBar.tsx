import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '../api/jobs'
import { useJobStore } from '../stores/jobStore'

const STEP_COUNT = 9

export function JobStatusBar() {
  const { activeJobId, openLog } = useJobStore()

  const { data: job } = useQuery({
    queryKey: ['job', activeJobId],
    queryFn: () => jobsApi.get(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'pending' ? 2000 : false
    },
  })

  if (!job) return null

  const stepNum   = typeof job.current_step === 'number' ? job.current_step : 0
  const progress  = Math.round((stepNum / STEP_COUNT) * 100)
  const isRunning = job.status === 'running' || job.status === 'pending'
  const isDone    = job.status === 'completed'
  const isFailed  = job.status === 'failed'

  const dotColor = isDone ? '#10b981' : isFailed ? '#ef4444' : '#4f83ff'
  const label = isDone
    ? '✓ Complete'
    : isFailed
    ? `Failed — ${job.failed_step_name ?? 'unknown step'}`
    : job.current_step_name ?? 'Starting…'

  return (
    <button
      onClick={openLog}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: '#0f0f13', border: '1px solid #1e1e26', borderRadius: 6,
        padding: '5px 12px', cursor: 'pointer', fontSize: 12,
        color: isDone ? '#10b981' : isFailed ? '#ef4444' : '#9999aa',
        transition: 'background 0.12s',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#141418' }}
      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#0f0f13' }}
    >
      {isRunning && (
        <span style={{
          width: 6, height: 6, borderRadius: '50%',
          background: dotColor, display: 'inline-block',
          animation: 'pulseDot 1.2s infinite',
        }} />
      )}
      <span>{label}</span>
      {isRunning && (
        <div style={{ width: 52, height: 2.5, background: '#1e1e26', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${progress}%`,
            background: '#4f83ff', borderRadius: 2, transition: 'width 0.5s',
          }} />
        </div>
      )}
      <span style={{ color: '#2a2a34', fontSize: 11 }}>logs</span>
    </button>
  )
}

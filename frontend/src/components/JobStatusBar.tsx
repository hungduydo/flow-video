import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '../api/jobs'
import { useJobStore } from '../stores/jobStore'

const STEP_NAMES = [
  'Download', 'Scene Cut', 'Extract Audio', 'Separate Audio',
  'Transcribe', 'Translate', 'TTS', 'Compose', 'Banner',
]

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

  const stepNum = typeof job.current_step === 'number' ? job.current_step : 0
  const progress = Math.round((stepNum / STEP_NAMES.length) * 100)
  const isRunning = job.status === 'running' || job.status === 'pending'

  const statusColor =
    job.status === 'completed' ? '#10b981' :
    job.status === 'failed' ? '#ef4444' :
    '#3b82f6'

  return (
    <div
      onClick={openLog}
      className="cursor-pointer flex items-center gap-3 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 hover:bg-slate-700 transition-colors"
    >
      {/* Status dot */}
      <span
        className={`w-2 h-2 rounded-full flex-shrink-0 ${isRunning ? 'animate-pulse' : ''}`}
        style={{ background: statusColor }}
      />

      {/* Step name */}
      <span className="text-sm text-slate-300 min-w-0 truncate">
        {job.status === 'completed'
          ? '✅ Complete'
          : job.status === 'failed'
          ? `❌ Failed at ${job.failed_step_name ?? 'unknown step'}`
          : job.current_step_name ?? 'Starting…'}
      </span>

      {/* Progress bar */}
      {isRunning && (
        <div className="flex-1 h-1.5 bg-slate-600 rounded-full overflow-hidden min-w-16">
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      <span className="text-xs text-slate-500 flex-shrink-0">View logs →</span>
    </div>
  )
}

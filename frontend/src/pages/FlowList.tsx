import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { flowsApi } from '../api/flows'
import { useJobStore } from '../stores/jobStore'
import type { FlowResponse } from '../types'

function cronLabel(schedule: string | null | undefined): string {
  if (!schedule) return ''
  // Simple human-readable labels for common patterns
  const known: Record<string, string> = {
    '0 9 * * *': 'Daily 9:00',
    '0 0 * * *': 'Daily midnight',
    '0 9 * * 1': 'Mon 9:00',
    '*/30 * * * *': 'Every 30 min',
  }
  return known[schedule] ?? schedule
}

function FlowCard({ flow }: { flow: FlowResponse }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { setActiveJob } = useJobStore()

  const runMutation = useMutation({
    mutationFn: () => flowsApi.run(flow.id),
    onSuccess: (job) => setActiveJob(job.job_id),
  })

  const deleteMutation = useMutation({
    mutationFn: () => flowsApi.delete(flow.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flows'] }),
  })

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 flex flex-col gap-3 hover:border-slate-600 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-100">{flow.name}</h3>
          <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xs">
            {flow.definition.url || <span className="italic">No URL set</span>}
          </p>
        </div>
        {flow.schedule && (
          <span className="text-xs bg-indigo-900/60 text-indigo-300 border border-indigo-700 rounded-full px-2 py-0.5 flex-shrink-0 ml-2">
            ⏰ {cronLabel(flow.schedule)}
          </span>
        )}
      </div>

      {/* Options summary */}
      <div className="flex flex-wrap gap-1.5">
        {[
          flow.definition.platform.toUpperCase(),
          flow.definition.translator,
          flow.definition.tts_provider,
          flow.definition.transcriber,
        ].map((tag) => (
          <span key={tag} className="text-xs bg-slate-700 text-slate-400 rounded px-2 py-0.5">
            {tag}
          </span>
        ))}
      </div>

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium py-2 rounded-lg transition-colors"
        >
          {runMutation.isPending ? 'Starting…' : '▶ Run'}
        </button>
        <button
          onClick={() => navigate(`/flows/${flow.id}`)}
          className="flex-1 bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm font-medium py-2 rounded-lg transition-colors"
        >
          ✏️ Edit
        </button>
        <button
          onClick={() => {
            if (confirm(`Delete "${flow.name}"?`)) deleteMutation.mutate()
          }}
          className="bg-slate-700 hover:bg-red-900/60 text-slate-400 hover:text-red-300 text-sm py-2 px-3 rounded-lg transition-colors"
        >
          🗑
        </button>
      </div>
    </div>
  )
}

export function FlowList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: flows, isLoading } = useQuery({
    queryKey: ['flows'],
    queryFn: flowsApi.list,
    refetchInterval: 5000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      flowsApi.create({
        name: 'New Flow',
        definition: {
          url: '',
          model: 'large-v3',
          transcriber: 'whisper',
          translator: 'gemini',
          tts_provider: 'edge_tts',
          platform: 'youtube',
          show_subtitle: true,
          crf: 23,
          force: false,
          output_dir: 'output',
        },
        enabled: true,
      }),
    onSuccess: (flow) => {
      qc.invalidateQueries({ queryKey: ['flows'] })
      navigate(`/flows/${flow.id}`)
    },
  })

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Flow Video</h1>
          <p className="text-sm text-slate-500 mt-1">Bilibili → Vietnamese dubbing pipeline</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/scheduler')}
            className="bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            ⏰ Scheduler
          </button>
          <button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-bold px-4 py-2 rounded-lg transition-colors"
          >
            + New Flow
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-slate-500 text-center py-20">Loading…</div>
      ) : !flows?.length ? (
        <div className="text-center py-20">
          <div className="text-5xl mb-4">🎬</div>
          <h2 className="text-lg font-semibold text-slate-300 mb-2">No flows yet</h2>
          <p className="text-slate-500 text-sm mb-6">Create your first flow to get started</p>
          <button
            onClick={() => createMutation.mutate()}
            className="bg-blue-600 hover:bg-blue-500 text-white font-bold px-6 py-3 rounded-lg transition-colors"
          >
            + Create Flow
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {flows.map((flow) => (
            <FlowCard key={flow.id} flow={flow} />
          ))}
        </div>
      )}
    </div>
  )
}

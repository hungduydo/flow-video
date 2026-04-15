import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { flowsApi } from '../api/flows'
import type { FlowResponse } from '../types'

// Simple cron presets
const PRESETS = [
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Daily at 9:00', value: '0 9 * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
  { label: 'Every Monday 9:00', value: '0 9 * * 1' },
  { label: 'Every 30 minutes', value: '*/30 * * * *' },
]

// Very basic human-readable cron display
function humanCron(cron: string): string {
  const match = PRESETS.find((p) => p.value === cron)
  if (match) return match.label
  return cron
}

function ScheduleModal({
  flow,
  onClose,
}: {
  flow: FlowResponse
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [cron, setCron] = useState(flow.schedule ?? '')
  const [usePreset, setUsePreset] = useState(true)

  const updateMutation = useMutation({
    mutationFn: (schedule: string | null) =>
      flowsApi.update(flow.id, { schedule }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flows'] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h3 className="text-base font-bold text-slate-100 mb-1">Edit Schedule</h3>
        <p className="text-sm text-slate-500 mb-5">{flow.name}</p>

        {/* Preset / custom toggle */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setUsePreset(true)}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${usePreset ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
          >
            Preset
          </button>
          <button
            onClick={() => setUsePreset(false)}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${!usePreset ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
          >
            Custom cron
          </button>
        </div>

        {usePreset ? (
          <div className="space-y-2 mb-5">
            {PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setCron(p.value)}
                className={`w-full text-left px-4 py-2.5 rounded-lg text-sm transition-colors ${
                  cron === p.value
                    ? 'bg-blue-600/20 border border-blue-500 text-blue-300'
                    : 'bg-slate-700/50 border border-slate-600 text-slate-300 hover:bg-slate-700'
                }`}
              >
                <span className="font-medium">{p.label}</span>
                <span className="text-slate-500 ml-2 font-mono text-xs">{p.value}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="mb-5">
            <label className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wide">
              Cron expression
            </label>
            <input
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 9 * * *"
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-blue-500"
            />
            <p className="text-xs text-slate-500 mt-1">
              Format: minute hour day month weekday
            </p>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => updateMutation.mutate(cron || null)}
            disabled={updateMutation.isPending}
            className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-bold py-2 rounded-lg transition-colors"
          >
            {updateMutation.isPending ? 'Saving…' : 'Save'}
          </button>
          {flow.schedule && (
            <button
              onClick={() => updateMutation.mutate(null)}
              className="bg-slate-700 hover:bg-red-900/50 text-slate-400 hover:text-red-300 text-sm py-2 px-3 rounded-lg transition-colors"
            >
              Remove
            </button>
          )}
          <button
            onClick={onClose}
            className="bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm py-2 px-4 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export function Scheduler() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [editingFlow, setEditingFlow] = useState<FlowResponse | null>(null)

  const { data: flows, isLoading } = useQuery({
    queryKey: ['flows'],
    queryFn: flowsApi.list,
    refetchInterval: 5000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      flowsApi.update(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flows'] }),
  })

  const scheduledFlows = flows?.filter((f) => f.schedule) ?? []
  const unscheduledFlows = flows?.filter((f) => !f.schedule) ?? []

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <button
          onClick={() => navigate('/')}
          className="text-slate-500 hover:text-slate-300 text-sm"
        >
          ← Back
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Scheduler</h1>
          <p className="text-sm text-slate-500 mt-1">Auto-run flows on a schedule</p>
        </div>
      </div>

      {isLoading ? (
        <div className="text-slate-500 text-center py-20">Loading…</div>
      ) : (
        <>
          {/* Scheduled flows */}
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Scheduled ({scheduledFlows.length})
          </h2>

          {scheduledFlows.length === 0 ? (
            <div className="bg-slate-800 border border-dashed border-slate-700 rounded-xl p-8 text-center mb-6">
              <p className="text-slate-500 text-sm">No scheduled flows yet</p>
            </div>
          ) : (
            <div className="space-y-2 mb-6">
              {scheduledFlows.map((flow) => (
                <div
                  key={flow.id}
                  className="flex items-center gap-4 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm text-slate-200 truncate">{flow.name}</div>
                    <div className="text-xs text-indigo-400 font-mono mt-0.5">
                      {humanCron(flow.schedule!)}
                      <span className="text-slate-600 ml-2">{flow.schedule}</span>
                    </div>
                  </div>

                  {/* Enabled toggle */}
                  <button
                    type="button"
                    onClick={() => toggleMutation.mutate({ id: flow.id, enabled: !flow.enabled })}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${flow.enabled ? 'bg-green-600' : 'bg-slate-600'}`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${flow.enabled ? 'translate-x-6' : 'translate-x-1'}`}
                    />
                  </button>

                  <button
                    onClick={() => setEditingFlow(flow)}
                    className="text-slate-500 hover:text-slate-300 text-sm px-2 py-1 rounded"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => navigate(`/flows/${flow.id}`)}
                    className="text-slate-500 hover:text-slate-300 text-sm px-2 py-1 rounded"
                  >
                    →
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Unscheduled flows — add schedule */}
          {unscheduledFlows.length > 0 && (
            <>
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Add schedule
              </h2>
              <div className="space-y-2">
                {unscheduledFlows.map((flow) => (
                  <div
                    key={flow.id}
                    className="flex items-center gap-4 bg-slate-800/50 border border-slate-700/50 rounded-xl px-4 py-3"
                  >
                    <div className="flex-1 text-sm text-slate-400 truncate">{flow.name}</div>
                    <button
                      onClick={() => setEditingFlow(flow)}
                      className="text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      + Schedule
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {editingFlow && (
        <ScheduleModal flow={editingFlow} onClose={() => setEditingFlow(null)} />
      )}
    </div>
  )
}

import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow, Background, BackgroundVariant, Controls,
} from '@xyflow/react'
import { flowsApi } from '../api/flows'
import { useFlowStore } from '../stores/flowStore'
import { useJobStore } from '../stores/jobStore'
import { StepNode } from '../components/nodes/StepNode'
import { ConfigPanel } from '../components/ConfigPanel'
import { JobStatusBar } from '../components/JobStatusBar'
import { LogDrawer } from '../components/LogDrawer'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const nodeTypes: Record<string, any> = { stepNode: StepNode }

export function FlowBuilder() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { setActiveJob } = useJobStore()

  const {
    nodes, edges, initFromDefinition,
    flowSchedule, flowEnabled,
    setFlowMeta, toDefinition,
  } = useFlowStore()

  const [name, setName] = useState('')
  const [editingName, setEditingName] = useState(false)

  const { data: flow } = useQuery({
    queryKey: ['flow', id],
    queryFn: () => flowsApi.get(id!),
    enabled: !!id,
  })

  useEffect(() => {
    if (flow) {
      initFromDefinition(flow.definition)
      setFlowMeta(flow.name, flow.schedule ?? null, flow.enabled)
      setName(flow.name)
    }
  }, [flow?.id])

  const saveMutation = useMutation({
    mutationFn: () =>
      flowsApi.update(id!, {
        name,
        definition: toDefinition(),
        schedule: flowSchedule ?? undefined,
        enabled: flowEnabled,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flows'] }),
  })

  const runMutation = useMutation({
    mutationFn: async () => {
      // Save first, then run
      await flowsApi.update(id!, { name, definition: toDefinition() })
      return flowsApi.run(id!)
    },
    onSuccess: (job) => {
      setActiveJob(job.job_id)
      qc.invalidateQueries({ queryKey: ['flows'] })
    },
  })

  const onNameKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === 'Escape') setEditingName(false)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-slate-900">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-800 bg-slate-900 z-10">
        <button
          onClick={() => navigate('/')}
          className="text-slate-500 hover:text-slate-300 text-sm mr-1"
        >
          ← Back
        </button>

        {editingName ? (
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setEditingName(false)}
            onKeyDown={onNameKeyDown}
            className="bg-slate-800 border border-blue-500 rounded px-2 py-1 text-sm font-bold text-slate-100 focus:outline-none w-48"
          />
        ) : (
          <button
            onClick={() => setEditingName(true)}
            className="text-sm font-bold text-slate-100 hover:text-blue-400 transition-colors"
          >
            {name || 'Untitled Flow'} ✏️
          </button>
        )}

        <div className="flex-1" />

        {/* Job status */}
        <JobStatusBar />

        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {saveMutation.isPending ? 'Saving…' : '💾 Save'}
        </button>
        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-bold px-4 py-2 rounded-lg transition-colors"
        >
          {runMutation.isPending ? 'Starting…' : '▶ Run'}
        </button>
      </div>

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Canvas */}
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={true}
            colorMode="dark"
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1e2433" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        {/* Config panel */}
        <div
          className="w-72 border-l border-slate-800 bg-slate-900 flex flex-col overflow-hidden"
        >
          <ConfigPanel />
        </div>
      </div>

      {/* Log drawer */}
      <LogDrawer />
    </div>
  )
}

import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ReactFlow, Background, BackgroundVariant, Controls } from '@xyflow/react'
import { flowsApi } from '../api/flows'
import { jobsApi } from '../api/jobs'
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
  const { setActiveJob, activeJobId } = useJobStore()

  const {
    nodes, edges, initFromDefinition,
    flowSchedule, flowEnabled,
    setFlowMeta, toDefinition,
    setJobStep, resetJobState,
  } = useFlowStore()

  const [name, setName] = useState('')
  const [editingName, setEditingName] = useState(false)
  const [saveLabel, setSaveLabel] = useState('Save')

  const { data: flow } = useQuery({
    queryKey: ['flow', id],
    queryFn: () => flowsApi.get(id!),
    enabled: !!id,
  })

  // Poll active job to update node step indicators
  const { data: activeJob } = useQuery({
    queryKey: ['job', activeJobId],
    queryFn: () => jobsApi.get(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'running' || s === 'pending' ? 2000 : false
    },
  })

  useEffect(() => {
    if (flow) {
      initFromDefinition(flow.definition)
      setFlowMeta(flow.name, flow.schedule ?? null, flow.enabled)
      setName(flow.name)
    }
  }, [flow?.id])

  // Sync job step progress into flowStore for node visual updates
  useEffect(() => {
    if (!activeJob) return
    if (activeJob.status === 'running' || activeJob.status === 'pending') {
      setJobStep(typeof activeJob.current_step === 'number' ? activeJob.current_step : 0)
    } else {
      resetJobState()
    }
  }, [activeJob?.current_step, activeJob?.status])

  const saveMutation = useMutation({
    mutationFn: () =>
      flowsApi.update(id!, {
        name, definition: toDefinition(),
        schedule: flowSchedule ?? undefined,
        enabled: flowEnabled,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flows'] })
      setSaveLabel('Saved ✓')
      setTimeout(() => setSaveLabel('Save'), 2000)
    },
  })

  const runMutation = useMutation({
    mutationFn: async () => {
      await flowsApi.update(id!, { name, definition: toDefinition() })
      return flowsApi.run(id!)
    },
    onSuccess: (job) => {
      setActiveJob(job.job_id)
      qc.invalidateQueries({ queryKey: ['flows'] })
      resetJobState()
    },
  })

  const onNameKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === 'Escape') setEditingName(false)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0b0b0d' }}>

      {/* ── Top bar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '0 16px', height: 50, flexShrink: 0,
        borderBottom: '1px solid #131318', background: '#0b0b0d', zIndex: 50,
      }}>
        {/* Back */}
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'none', border: 'none', color: '#555566', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 4, fontSize: 13,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M9 2L4 7L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Flows
        </button>

        <span style={{ color: '#1a1a22', fontSize: 16 }}>/</span>

        {/* Flow name (editable) */}
        {editingName ? (
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onBlur={() => setEditingName(false)}
            onKeyDown={onNameKeyDown}
            style={{
              background: '#111114', border: '1px solid #4f83ff',
              borderRadius: 5, padding: '3px 8px',
              fontSize: 13, fontWeight: 600, color: '#e8e8f0',
              outline: 'none', width: 200,
            }}
          />
        ) : (
          <button
            onClick={() => setEditingName(true)}
            style={{
              background: 'none', border: 'none', color: '#d0d0e0',
              cursor: 'pointer', fontSize: 13, fontWeight: 600,
              padding: '3px 6px', borderRadius: 4,
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            {name || 'Untitled'}
            <svg width="9" height="9" viewBox="0 0 10 10" fill="none">
              <path d="M1 7.5L7.5 1L9 2.5L2.5 9L1 9L1 7.5Z" stroke="#333340" strokeWidth="1" strokeLinejoin="round" />
            </svg>
          </button>
        )}

        {/* Node/edge count chip */}
        <span style={{
          fontSize: 11, color: '#2a2a34', background: '#0f0f13',
          border: '1px solid #1a1a1f', borderRadius: 4,
          padding: '2px 7px', fontFamily: "'DM Mono', monospace",
        }}>
          {nodes.length} nodes · {edges.length} edges
        </span>

        <div style={{ flex: 1 }} />

        {/* Job status chip */}
        <JobStatusBar />

        {/* Save */}
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#222228' }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#1a1a1f' }}
          style={{
            background: '#1a1a1f', border: '1px solid #222228', borderRadius: 6,
            padding: '4px 10px', fontSize: 12, fontWeight: 500,
            color: '#c0c0cc', cursor: saveMutation.isPending ? 'not-allowed' : 'pointer',
            opacity: saveMutation.isPending ? 0.45 : 1, transition: 'background 0.12s',
          }}
        >
          {saveLabel}
        </button>

        {/* Run */}
        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          onMouseEnter={e => { if (!runMutation.isPending) (e.currentTarget as HTMLButtonElement).style.background = '#6b96ff' }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#4f83ff' }}
          style={{
            background: '#4f83ff', border: '1px solid #4f83ff', borderRadius: 6,
            padding: '4px 10px', fontSize: 12, fontWeight: 500, color: '#fff',
            cursor: runMutation.isPending ? 'not-allowed' : 'pointer',
            opacity: runMutation.isPending ? 0.45 : 1, transition: 'background 0.12s',
          }}
        >
          ▶ Run
        </button>
      </div>

      {/* ── Hint bar ── */}
      <div style={{
        padding: '6px 20px', borderBottom: '1px solid #0f0f14',
        background: '#0d0d10', fontSize: 11, color: '#2a2a34',
        display: 'flex', gap: 20, flexShrink: 0,
      }}>
        <span>Click node to configure</span>
        <span>·</span>
        <span>Click edge to delete</span>
        <span>·</span>
        <span>Drag to pan canvas</span>
      </div>

      {/* ── Main area ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>

        {/* Canvas */}
        <div style={{ flex: 1, position: 'relative' }}>
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
            style={{ background: '#0b0b0d' }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={24} size={1}
              color="#1c1c26"
            />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        {/* Config panel */}
        <div style={{
          width: 300, borderLeft: '1px solid #131318',
          display: 'flex', flexDirection: 'column',
          overflowY: 'auto', background: '#0b0b0d', flexShrink: 0,
        }}>
          <ConfigPanel />
        </div>

        {/* Log drawer (absolute within main area) */}
        <LogDrawer />
      </div>
    </div>
  )
}

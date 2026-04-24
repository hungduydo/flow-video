import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { flowsApi } from '../api/flows'
import { useJobStore } from '../stores/jobStore'
import type { FlowResponse } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

const CRON_LABELS: Record<string, string> = {
  '0 9 * * *':    'Daily 9:00',
  '0 0 * * *':    'Daily midnight',
  '0 9 * * 1':    'Mon 9:00',
  '*/30 * * * *': 'Every 30 min',
  '0 * * * *':    'Every hour',
}
function cronLabel(s: string | null | undefined) {
  if (!s) return ''
  return CRON_LABELS[s] ?? s
}

// ── Primitive components ──────────────────────────────────────────────────────

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 4,
      fontSize: 11, fontWeight: 500, background: '#18181c',
      color: '#5a5a6a', border: '1px solid #222228',
      fontFamily: "'DM Mono', monospace", letterSpacing: '0.01em',
    }}>
      {children}
    </span>
  )
}

function Badge({ children, color = '#4f83ff', mono = false }: {
  children: React.ReactNode
  color?: string
  mono?: boolean
}) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '2px 7px', borderRadius: 4,
      fontSize: 11, fontWeight: 500,
      background: color + '18', color,
      border: `1px solid ${color}30`,
      fontFamily: mono ? "'DM Mono', monospace" : 'inherit',
    }}>
      {children}
    </span>
  )
}

function Btn({
  children, onClick, disabled = false, variant = 'ghost', size = 'md',
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'subtle' | 'ghost' | 'danger' | 'success'
  size?: 'sm' | 'md'
}) {
  const [hov, setHov] = useState(false)
  const base: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    border: '1px solid transparent', borderRadius: 6,
    padding: size === 'sm' ? '4px 10px' : '6px 14px',
    fontSize: size === 'sm' ? 12 : 13, fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.45 : 1,
    transition: 'background 0.12s, border-color 0.12s, color 0.12s',
    whiteSpace: 'nowrap', outline: 'none', letterSpacing: '-0.01em',
  }
  const variants: Record<string, React.CSSProperties> = {
    primary: { background: hov ? '#6b96ff' : '#4f83ff', color: '#fff', borderColor: hov ? '#6b96ff' : '#4f83ff' },
    subtle:  { background: hov ? '#222228' : '#1a1a1f', color: hov ? '#e8e8f0' : '#c0c0cc', borderColor: '#222228' },
    ghost:   { background: hov ? '#1a1a1f' : 'transparent', color: hov ? '#d0d0da' : '#6b6b7a', borderColor: hov ? '#222228' : 'transparent' },
    danger:  { background: hov ? '#2a1010' : 'transparent', color: '#ef4444', borderColor: hov ? '#3a1818' : '#222228' },
    success: { background: hov ? '#0d2a1e' : '#0a1f17', color: '#10b981', borderColor: '#0f3425' },
  }
  return (
    <button
      onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ ...base, ...variants[variant] }}
    >
      {children}
    </button>
  )
}

// ── FlowCard ──────────────────────────────────────────────────────────────────

function FlowCard({ flow, onEdit, onRun, onDelete, isRunning }: {
  flow: FlowResponse
  onEdit: (id: string) => void
  onRun: (id: string) => void
  onDelete: (id: string) => void
  isRunning: boolean
}) {
  const [hov, setHov] = useState(false)
  const d = flow.definition

  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: '#111114',
        border: `1px solid ${hov ? '#2e2e38' : '#1e1e24'}`,
        borderRadius: 10, padding: '18px 18px 14px',
        display: 'flex', flexDirection: 'column', gap: 14,
        transition: 'border-color 0.15s',
        animation: 'fadeIn 0.15s ease',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#e8e8f0', letterSpacing: '-0.02em' }}>
              {flow.name}
            </span>
            {!flow.enabled && <Badge color="#555566">paused</Badge>}
          </div>
          <div style={{
            fontSize: 11, color: '#3a3a44',
            fontFamily: "'DM Mono', monospace",
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            maxWidth: 260,
          }}>
            {d.url || <span style={{ fontStyle: 'italic' }}>no url</span>}
          </div>
        </div>
        {flow.schedule && (
          <Badge color="#f59e0b" mono>⏱ {cronLabel(flow.schedule)}</Badge>
        )}
      </div>

      {/* Tags */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        <Tag>{d.platform}</Tag>
        <Tag>{d.transcriber}</Tag>
        <Tag>{d.translator}</Tag>
        <Tag>{d.tts_provider}</Tag>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={() => onRun(flow.id)}
          disabled={isRunning}
          style={{
            flex: 1,
            background: isRunning ? '#0e1a30' : '#4f83ff',
            color: isRunning ? '#4f83ff' : '#fff',
            border: `1px solid ${isRunning ? '#1a3060' : '#4f83ff'}`,
            borderRadius: 6, padding: '7px 0',
            fontSize: 12, fontWeight: 600,
            cursor: isRunning ? 'default' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            transition: 'all 0.15s',
          }}
        >
          {isRunning ? (
            <>
              <span style={{
                width: 7, height: 7, borderRadius: '50%',
                background: '#4f83ff', display: 'inline-block',
                animation: 'pulseDot 1.2s ease-in-out infinite',
              }} />
              Running
            </>
          ) : '▶ Run'}
        </button>
        <Btn onClick={() => onEdit(flow.id)} variant="subtle" size="sm">Edit</Btn>
        <Btn onClick={() => onDelete(flow.id)} variant="danger" size="sm">✕</Btn>
      </div>
    </div>
  )
}

// ── FlowList page ─────────────────────────────────────────────────────────────

export function FlowList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { setActiveJob } = useJobStore()

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
          url: '', model: 'large-v3', transcriber: 'whisper',
          translator: 'gemini', tts_provider: 'edge_tts',
          platform: 'youtube', show_subtitle: true, crf: 23,
          force: false, output_dir: 'output',
        },
        enabled: true,
      }),
    onSuccess: (flow) => {
      qc.invalidateQueries({ queryKey: ['flows'] })
      navigate(`/flows/${flow.id}`)
    },
  })

  const runMutation = useMutation({
    mutationFn: (id: string) => flowsApi.run(id),
    onSuccess: (job) => setActiveJob(job.job_id),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => flowsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flows'] }),
  })

  return (
    <div style={{ minHeight: '100vh', padding: '36px 44px', maxWidth: 1120, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 36 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <rect x="2" y="2" width="7" height="7" rx="1.5" fill="#4f83ff" />
              <rect x="11" y="2" width="7" height="7" rx="1.5" fill="#4f83ff" opacity="0.5" />
              <rect x="2" y="11" width="7" height="7" rx="1.5" fill="#4f83ff" opacity="0.5" />
              <rect x="11" y="11" width="7" height="7" rx="1.5" fill="#4f83ff" opacity="0.3" />
            </svg>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: '#e8e8f0', letterSpacing: '-0.03em', lineHeight: 1 }}>
              Flow Video
            </h1>
          </div>
          <p style={{ fontSize: 13, color: '#3a3a44', letterSpacing: '-0.01em' }}>
            Bilibili → Vietnamese dubbing pipeline
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn onClick={() => navigate('/scheduler')} variant="subtle">Scheduler</Btn>
          <Btn onClick={() => createMutation.mutate()} disabled={createMutation.isPending} variant="primary">
            + New Flow
          </Btn>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '100px 0', color: '#3a3a44', fontSize: 13 }}>
          Loading…
        </div>
      ) : !flows?.length ? (
        <div style={{ textAlign: 'center', padding: '100px 0', color: '#3a3a44' }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            border: '1px dashed #222228',
            margin: '0 auto 20px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M10 4v12M4 10h12" stroke="#3a3a44" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <p style={{ fontSize: 14, color: '#555566', marginBottom: 20 }}>No flows yet</p>
          <Btn onClick={() => createMutation.mutate()} variant="primary">Create your first flow</Btn>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))', gap: 10 }}>
          {flows.map(f => (
            <FlowCard
              key={f.id} flow={f}
              onEdit={(id) => navigate(`/flows/${id}`)}
              onRun={(id) => runMutation.mutate(id)}
              onDelete={(id) => { if (window.confirm(`Delete "${f.name}"?`)) deleteMutation.mutate(id) }}
              isRunning={runMutation.isPending && runMutation.variables === f.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

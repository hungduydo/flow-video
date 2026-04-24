import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { flowsApi } from '../api/flows'
import type { FlowResponse } from '../types'

// ── Presets ───────────────────────────────────────────────────────────────────

const PRESETS = [
  { label: 'Every hour',     value: '0 * * * *' },
  { label: 'Daily at 9:00', value: '0 9 * * *' },
  { label: 'Daily midnight', value: '0 0 * * *' },
  { label: 'Mon at 9:00',   value: '0 9 * * 1' },
  { label: 'Every 30 min',  value: '*/30 * * * *' },
]

function humanCron(cron: string) {
  return PRESETS.find(p => p.value === cron)?.label ?? cron
}

// ── Primitive components ──────────────────────────────────────────────────────

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      style={{
        width: 38, height: 21, borderRadius: 11,
        background: value ? '#4f83ff' : '#222228',
        border: 'none', cursor: 'pointer', padding: 0,
        position: 'relative', transition: 'background 0.18s', flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: 2.5, left: value ? 19 : 2.5,
        width: 16, height: 16, borderRadius: 8,
        background: '#fff', transition: 'left 0.18s',
        boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
      }} />
    </button>
  )
}

function Btn({
  children, onClick, disabled = false, variant = 'ghost', style: extraStyle = {},
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'subtle' | 'ghost' | 'danger'
  style?: React.CSSProperties
}) {
  const [hov, setHov] = useState(false)
  const base: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    border: '1px solid transparent', borderRadius: 6, padding: '4px 10px',
    fontSize: 12, fontWeight: 500, cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.45 : 1,
    transition: 'background 0.12s, border-color 0.12s, color 0.12s',
    whiteSpace: 'nowrap', outline: 'none',
  }
  const variants: Record<string, React.CSSProperties> = {
    primary: { background: hov ? '#6b96ff' : '#4f83ff', color: '#fff', borderColor: hov ? '#6b96ff' : '#4f83ff' },
    subtle:  { background: hov ? '#222228' : '#1a1a1f', color: hov ? '#e8e8f0' : '#c0c0cc', borderColor: '#222228' },
    ghost:   { background: hov ? '#1a1a1f' : 'transparent', color: hov ? '#d0d0da' : '#6b6b7a', borderColor: hov ? '#222228' : 'transparent' },
    danger:  { background: hov ? '#2a1010' : 'transparent', color: '#ef4444', borderColor: hov ? '#3a1818' : '#222228' },
  }
  return (
    <button
      onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ ...base, ...variants[variant], ...extraStyle }}
    >
      {children}
    </button>
  )
}

// ── Schedule Modal ────────────────────────────────────────────────────────────

function ScheduleModal({ flow, onClose }: { flow: FlowResponse; onClose: () => void }) {
  const qc = useQueryClient()
  const [cron, setCron] = useState(flow.schedule ?? '')
  const [tab, setTab] = useState<'preset' | 'custom'>('preset')

  const updateMutation = useMutation({
    mutationFn: (schedule: string | null) => flowsApi.update(flow.id, { schedule }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['flows'] }); onClose() },
  })

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
    }}>
      <div style={{
        background: '#111114', border: '1px solid #1e1e26',
        borderRadius: 12, padding: '24px 24px 20px', width: 420,
        boxShadow: '0 24px 60px rgba(0,0,0,0.6)', animation: 'fadeIn 0.15s ease',
      }}>
        <div style={{ marginBottom: 18 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e8f0', marginBottom: 3, letterSpacing: '-0.02em' }}>
            Schedule
          </h3>
          <p style={{ fontSize: 12, color: '#3a3a44' }}>{flow.name}</p>
        </div>

        {/* Tab strip */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: '#0d0d10', borderRadius: 7, padding: 3 }}>
          {(['preset', 'custom'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                flex: 1, background: tab === t ? '#1e1e26' : 'transparent',
                border: 'none', borderRadius: 5, padding: '6px 0',
                fontSize: 12, fontWeight: 500,
                color: tab === t ? '#d0d0da' : '#3a3a44',
                cursor: 'pointer', transition: 'background 0.12s, color 0.12s',
              }}
            >
              {t === 'preset' ? 'Preset' : 'Custom cron'}
            </button>
          ))}
        </div>

        {tab === 'preset' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 20 }}>
            {PRESETS.map(p => {
              const sel = cron === p.value
              return (
                <button
                  key={p.value} onClick={() => setCron(p.value)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 12px', borderRadius: 7, cursor: 'pointer',
                    border: `1px solid ${sel ? '#4f83ff50' : '#1e1e26'}`,
                    background: sel ? '#4f83ff0e' : '#0d0d10',
                    textAlign: 'left', transition: 'all 0.12s',
                  }}
                >
                  <span style={{ fontSize: 13, color: sel ? '#7aaaff' : '#9999aa', fontWeight: sel ? 500 : 400 }}>
                    {p.label}
                  </span>
                  <span style={{ fontSize: 11, color: '#333340', fontFamily: "'DM Mono', monospace" }}>
                    {p.value}
                  </span>
                </button>
              )
            })}
          </div>
        ) : (
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#555566', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Cron expression
              <span style={{ fontSize: 10, color: '#3a3a44', marginLeft: 6, textTransform: 'none', letterSpacing: 0 }}>minute · hour · day · month · weekday</span>
            </label>
            <input
              value={cron} onChange={e => setCron(e.target.value)}
              placeholder="0 9 * * *"
              style={{
                width: '100%', background: '#0d0d10', border: '1px solid #222228',
                borderRadius: 6, padding: '8px 10px', fontSize: 13,
                color: '#e0e0ec', outline: 'none',
                fontFamily: "'DM Mono', monospace", letterSpacing: '0.03em',
              }}
            />
            {cron && (
              <p style={{ fontSize: 11, color: '#4f83ff', marginTop: 6 }}>→ {humanCron(cron)}</p>
            )}
          </div>
        )}

        <div style={{ display: 'flex', gap: 7 }}>
          <Btn
            onClick={() => updateMutation.mutate(cron || null)}
            disabled={updateMutation.isPending}
            variant="primary"
            style={{ flex: 1, padding: '7px 14px', fontSize: 13 }}
          >
            {updateMutation.isPending ? 'Saving…' : 'Save schedule'}
          </Btn>
          {flow.schedule && (
            <Btn onClick={() => updateMutation.mutate(null)} variant="danger">Remove</Btn>
          )}
          <Btn onClick={onClose} variant="ghost">Cancel</Btn>
        </div>
      </div>
    </div>
  )
}

// ── Schedule Row ──────────────────────────────────────────────────────────────

function ScheduleRow({ flow, onEdit, onToggle }: {
  flow: FlowResponse
  onEdit: () => void
  onToggle: () => void
}) {
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '11px 16px', background: '#111114',
        border: `1px solid ${hov ? '#2a2a34' : '#1e1e24'}`,
        borderRadius: 8, transition: 'border-color 0.12s',
      }}
    >
      <Toggle value={flow.enabled} onChange={onToggle} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: '#d0d0da', letterSpacing: '-0.01em', marginBottom: 2 }}>
          {flow.name}
        </div>
        <div style={{ fontSize: 11, color: '#555566', fontFamily: "'DM Mono', monospace" }}>
          {humanCron(flow.schedule!)}
          <span style={{ color: '#282830', marginLeft: 8 }}>{flow.schedule}</span>
        </div>
      </div>
      <Btn onClick={onEdit} variant="ghost">Edit</Btn>
    </div>
  )
}

// ── Scheduler page ────────────────────────────────────────────────────────────

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

  const scheduledFlows = flows?.filter(f => f.schedule) ?? []
  const unscheduledFlows = flows?.filter(f => !f.schedule) ?? []

  return (
    <div style={{ minHeight: '100vh', padding: '36px 44px', maxWidth: 760, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 36 }}>
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'none', border: 'none', color: '#555566', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, padding: '4px 0',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M9 2L4 7L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: '#e8e8f0', letterSpacing: '-0.03em', marginBottom: 2 }}>
            Scheduler
          </h1>
          <p style={{ fontSize: 13, color: '#3a3a44' }}>Auto-run flows on a schedule</p>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '80px 0', color: '#3a3a44', fontSize: 13 }}>Loading…</div>
      ) : (
        <>
          {/* Scheduled section */}
          <div style={{ fontSize: 10.5, fontWeight: 700, color: '#3a3a44', textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 8 }}>
            Scheduled ({scheduledFlows.length})
          </div>
          {scheduledFlows.length === 0 ? (
            <div style={{
              border: '1px dashed #1a1a1f', borderRadius: 8,
              padding: '28px 0', textAlign: 'center',
              color: '#2a2a34', fontSize: 12, marginBottom: 28,
            }}>
              No scheduled flows
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 28 }}>
              {scheduledFlows.map(f => (
                <ScheduleRow
                  key={f.id} flow={f}
                  onEdit={() => setEditingFlow(f)}
                  onToggle={() => toggleMutation.mutate({ id: f.id, enabled: !f.enabled })}
                />
              ))}
            </div>
          )}

          {/* Unscheduled section */}
          {unscheduledFlows.length > 0 && (
            <>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: '#3a3a44', textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 8 }}>
                Unscheduled ({unscheduledFlows.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {unscheduledFlows.map(f => (
                  <div
                    key={f.id}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '10px 16px', background: '#0e0e11',
                      border: '1px solid #161620', borderRadius: 8,
                    }}
                  >
                    <span style={{ fontSize: 13, color: '#444454' }}>{f.name}</span>
                    <Btn onClick={() => setEditingFlow(f)} variant="subtle">+ Schedule</Btn>
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

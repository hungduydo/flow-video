import { useState } from 'react'
import { useFlowStore, STEP_DEFS } from '../stores/flowStore'
import type { JobCreateRequest } from '../types'

// ── Primitive components ──────────────────────────────────────────────────────

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label style={{
        display: 'block', fontSize: 11, fontWeight: 600, color: '#555566',
        marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.07em',
      }}>
        {label}
      </label>
      {children}
      {hint && <p style={{ fontSize: 11, color: '#3a3a44', marginTop: 5, lineHeight: 1.4 }}>{hint}</p>}
    </div>
  )
}

function TextInput({ value, onChange, placeholder, type = 'text', mono = false }: {
  value: string | number
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  mono?: boolean
}) {
  const [foc, setFoc] = useState(false)
  return (
    <input
      type={type} value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      onFocus={() => setFoc(true)} onBlur={() => setFoc(false)}
      style={{
        width: '100%', background: '#0d0d10',
        border: `1px solid ${foc ? '#4f83ff' : '#222228'}`,
        borderRadius: 6, padding: '7px 10px', fontSize: 13,
        color: '#e0e0ec', outline: 'none',
        fontFamily: mono ? "'DM Mono', monospace" : 'inherit',
        transition: 'border-color 0.15s',
      }}
    />
  )
}

function SelectInput<T extends string>({ value, onChange, options }: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
}) {
  const [foc, setFoc] = useState(false)
  return (
    <select
      value={value} onChange={e => onChange(e.target.value as T)}
      onFocus={() => setFoc(true)} onBlur={() => setFoc(false)}
      style={{
        width: '100%', background: '#0d0d10',
        border: `1px solid ${foc ? '#4f83ff' : '#222228'}`,
        borderRadius: 6, padding: '7px 10px', fontSize: 13,
        color: '#e0e0ec', outline: 'none', cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

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

// ── ConfigPanel ───────────────────────────────────────────────────────────────

export function ConfigPanel() {
  const { nodes, selectedNodeId, selectNode, updateNodeConfig } = useFlowStore()
  const node = nodes.find(n => n.id === selectedNodeId)
  const stepDef = STEP_DEFS.find(s => s.key === selectedNodeId)

  if (!node || !stepDef) {
    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        color: '#2a2a34', padding: 28, textAlign: 'center', gap: 10,
      }}>
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="10" stroke="#1e1e28" strokeWidth="1.5" />
          <path d="M16 11v5l3 3" stroke="#1e1e28" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span style={{ fontSize: 12, color: '#2a2a34', lineHeight: 1.7 }}>Click a node<br />to configure it</span>
      </div>
    )
  }

  const cfg = node.data.config as Partial<JobCreateRequest>
  const upd = (patch: Partial<JobCreateRequest>) => updateNodeConfig(node.id, patch)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 22px' }}>
      {/* Panel header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 22, paddingBottom: 14, borderBottom: '1px solid #1a1a1f',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: stepDef.color }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: '#e8e8f0', letterSpacing: '-0.02em' }}>
            {stepDef.label}
          </span>
          <span style={{ fontSize: 12, color: '#2a2a34' }}>— {stepDef.description ?? ''}</span>
        </div>
        <button
          onClick={() => selectNode(null)}
          style={{ background: 'none', border: 'none', color: '#3a3a44', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}
        >
          ✕
        </button>
      </div>

      {/* Fields per step */}
      {selectedNodeId === 'download' && (
        <>
          <Field label="Bilibili URL">
            <TextInput value={cfg.url ?? ''} onChange={v => upd({ url: v })} placeholder="https://www.bilibili.com/video/BV…" mono />
          </Field>
          <Field label="Output directory">
            <TextInput value={cfg.output_dir ?? 'output'} onChange={v => upd({ output_dir: v })} mono />
          </Field>
          <Field label="Cookies file" hint="Optional — for members-only content">
            <TextInput value={cfg.cookies_file ?? ''} onChange={v => upd({ cookies_file: v || null })} placeholder="path/to/cookies.txt" mono />
          </Field>
        </>
      )}

      {selectedNodeId === 'transcribe' && (
        <>
          <Field label="Provider">
            <SelectInput
              value={cfg.transcriber ?? 'whisper'}
              onChange={v => upd({ transcriber: v })}
              options={[
                { value: 'whisper', label: 'Whisper — local' },
                { value: 'deepgram', label: 'Deepgram — cloud' },
              ]}
            />
          </Field>
          <Field label="Whisper model" hint="Larger = more accurate, slower">
            <SelectInput
              value={cfg.model ?? 'large-v3'}
              onChange={v => upd({ model: v })}
              options={[
                { value: 'large-v3', label: 'large-v3 — best' },
                { value: 'large-v2', label: 'large-v2' },
                { value: 'medium',   label: 'medium' },
                { value: 'small',    label: 'small' },
                { value: 'base',     label: 'base — fastest' },
              ]}
            />
          </Field>
        </>
      )}

      {selectedNodeId === 'translate' && (
        <Field label="Provider">
          <SelectInput
            value={cfg.translator ?? 'gemini'}
            onChange={v => upd({ translator: v })}
            options={[
              { value: 'gemini',      label: 'Gemini 2.0 Flash' },
              { value: 'claude',      label: 'Claude Sonnet' },
              { value: 'ollama_cloud', label: 'Ollama Cloud' },
              { value: 'ollama',      label: 'Ollama — local' },
            ]}
          />
        </Field>
      )}

      {selectedNodeId === 'tts' && (
        <Field label="Provider">
          <SelectInput
            value={cfg.tts_provider ?? 'edge_tts'}
            onChange={v => upd({ tts_provider: v })}
            options={[
              { value: 'edge_tts',   label: 'Edge TTS — free' },
              { value: 'elevenlabs', label: 'ElevenLabs — premium' },
            ]}
          />
        </Field>
      )}

      {selectedNodeId === 'compose' && (
        <>
          <Field label="Platform">
            <SelectInput
              value={cfg.platform ?? 'youtube'}
              onChange={v => upd({ platform: v })}
              options={[
                { value: 'youtube', label: 'YouTube — 16:9' },
                { value: 'tiktok',  label: 'TikTok — 9:16' },
                { value: 'both',    label: 'Both' },
              ]}
            />
          </Field>
          <Field label="CRF quality" hint="0–51. Lower = better quality, larger file">
            <TextInput type="number" value={cfg.crf ?? 23} onChange={v => upd({ crf: Number(v) })} />
          </Field>
          <Field label="Burn subtitles">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Toggle value={cfg.show_subtitle ?? true} onChange={v => upd({ show_subtitle: v })} />
              <span style={{ fontSize: 12, color: '#555566' }}>{cfg.show_subtitle ? 'On' : 'Off'}</span>
            </div>
          </Field>
          {(cfg.platform === 'tiktok' || cfg.platform === 'both') && (
            <Field label="TikTok crop X offset">
              <TextInput type="number" value={cfg.tiktok_crop_x ?? ''} onChange={v => upd({ tiktok_crop_x: v ? Number(v) : null })} placeholder="e.g. 200" />
            </Field>
          )}
        </>
      )}

      {['scenes', 'extract', 'separate', 'banner'].includes(selectedNodeId ?? '') && (
        <p style={{
          fontSize: 12, color: '#3a3a44', background: '#0f0f13',
          borderRadius: 6, padding: '11px 14px', border: '1px solid #1a1a1f', lineHeight: 1.6,
        }}>
          This step runs automatically with no configurable options.
        </p>
      )}
    </div>
  )
}

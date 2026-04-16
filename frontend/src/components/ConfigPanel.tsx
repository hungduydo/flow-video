import { useFlowStore, STEP_DEFS } from '../stores/flowStore'
import type { JobCreateRequest } from '../types'

interface FieldProps {
  label: string
  children: React.ReactNode
}
function Field({ label, children }: FieldProps) {
  return (
    <div className="mb-4">
      <label className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wide">
        {label}
      </label>
      {children}
    </div>
  )
}

function Input({ value, onChange, placeholder, type = 'text' }: {
  value: string | number
  onChange: (v: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <input
      type={type}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
    />
  )
}

function Select<T extends string>({ value, onChange, options }: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${value ? 'bg-blue-600' : 'bg-slate-600'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`}
      />
      <span className="sr-only">{label}</span>
    </button>
  )
}

export function ConfigPanel() {
  const { nodes, selectedNodeId, selectNode, updateNodeConfig } = useFlowStore()
  const node = nodes.find((n) => n.id === selectedNodeId)
  const stepDef = STEP_DEFS.find((s) => s.key === selectedNodeId)

  if (!node || !stepDef) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 p-8 text-center">
        <div className="text-4xl mb-3">👆</div>
        <p className="text-sm">Click a step to configure it</p>
      </div>
    )
  }

  const cfg = node.data.config as Partial<JobCreateRequest>
  const upd = (patch: Partial<JobCreateRequest>) => updateNodeConfig(node.id, patch)

  return (
    <div className="p-4 overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{stepDef.icon}</span>
          <h3 className="text-base font-bold text-slate-100">{stepDef.label}</h3>
        </div>
        <button
          onClick={() => selectNode(null)}
          className="text-slate-500 hover:text-slate-300 text-lg leading-none"
        >
          ✕
        </button>
      </div>

      {selectedNodeId === 'download' && (
        <>
          <Field label="Video URL">
            <Input
              value={cfg.url ?? ''}
              onChange={(v) => upd({ url: v })}
              placeholder="https://www.bilibili.com/video/..."
            />
          </Field>
          <Field label="Output directory">
            <Input
              value={cfg.output_dir ?? 'output'}
              onChange={(v) => upd({ output_dir: v })}
            />
          </Field>
          <Field label="Cookies file (optional)">
            <Input
              value={cfg.cookies_file ?? ''}
              onChange={(v) => upd({ cookies_file: v || null })}
              placeholder="path/to/cookies.txt"
            />
          </Field>
        </>
      )}

      {selectedNodeId === 'transcribe' && (
        <>
          <Field label="Provider">
            <Select
              value={cfg.transcriber ?? 'whisper'}
              onChange={(v) => upd({ transcriber: v })}
              options={[
                { value: 'whisper', label: 'Whisper (local)' },
                { value: 'deepgram', label: 'Deepgram (cloud)' },
              ]}
            />
          </Field>
          <Field label="Whisper model">
            <Select
              value={cfg.model ?? 'large-v3'}
              onChange={(v) => upd({ model: v })}
              options={[
                { value: 'large-v3', label: 'large-v3 (best)' },
                { value: 'large-v2', label: 'large-v2' },
                { value: 'medium', label: 'medium' },
                { value: 'small', label: 'small' },
                { value: 'base', label: 'base (fastest)' },
              ]}
            />
          </Field>
        </>
      )}

      {selectedNodeId === 'translate' && (
        <Field label="Translation provider">
          <Select
            value={cfg.translator ?? 'gemini'}
            onChange={(v) => upd({ translator: v })}
            options={[
              { value: 'gemini', label: 'Gemini 2.0 Flash' },
              { value: 'ollama_cloud', label: 'Ollama Cloud' },
              { value: 'ollama', label: 'Ollama (local)' },
              { value: 'claude', label: 'Claude Sonnet' },
            ]}
          />
        </Field>
      )}

      {selectedNodeId === 'tts' && (
        <Field label="TTS provider">
          <Select
            value={cfg.tts_provider ?? 'edge_tts'}
            onChange={(v) => upd({ tts_provider: v })}
            options={[
              { value: 'edge_tts', label: 'Edge TTS (free)' },
              { value: 'elevenlabs', label: 'ElevenLabs (premium)' },
            ]}
          />
        </Field>
      )}

      {selectedNodeId === 'compose' && (
        <>
          <Field label="Platform">
            <Select
              value={cfg.platform ?? 'youtube'}
              onChange={(v) => upd({ platform: v })}
              options={[
                { value: 'youtube', label: 'YouTube (16:9)' },
                { value: 'tiktok', label: 'TikTok (9:16)' },
                { value: 'both', label: 'Both' },
              ]}
            />
          </Field>
          <Field label="CRF quality (0–51, lower = better)">
            <Input
              type="number"
              value={cfg.crf ?? 23}
              onChange={(v) => upd({ crf: Number(v) })}
            />
          </Field>
          <Field label="Show subtitles">
            <Toggle
              value={cfg.show_subtitle ?? true}
              onChange={(v) => upd({ show_subtitle: v })}
              label="Show subtitles"
            />
          </Field>
          {(cfg.platform === 'tiktok' || cfg.platform === 'both') && (
            <Field label="TikTok crop X offset (optional)">
              <Input
                type="number"
                value={cfg.tiktok_crop_x ?? ''}
                onChange={(v) => upd({ tiktok_crop_x: v ? Number(v) : null })}
              />
            </Field>
          )}
        </>
      )}

      {selectedNodeId === 'banner' && (
        <div className="text-slate-500 text-sm bg-slate-800/50 rounded-lg p-3">
          Banner thumbnails are generated automatically using the platform set in the Compose step.
        </div>
      )}

      {['scenes', 'extract', 'separate'].includes(selectedNodeId ?? '') && (
        <div className="text-slate-500 text-sm bg-slate-800/50 rounded-lg p-3">
          This step runs automatically with no configurable options.
        </div>
      )}
    </div>
  )
}

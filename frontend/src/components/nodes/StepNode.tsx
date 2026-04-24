import { memo, useState } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { useFlowStore, STEP_DEFS, type StepNodeData } from '../../stores/flowStore'

type StepNodeType = Node<StepNodeData, 'stepNode'>

// Maps step key → color
const COLOR_MAP: Record<string, string> = Object.fromEntries(
  STEP_DEFS.map(s => [s.key, s.color])
)

// Maps step key → short description (mirrors the FlowBuilder.jsx ALL_STEPS)
const DESC_MAP: Record<string, string> = {
  download:   'Fetch from Bilibili',
  scenes:     'Detect cuts',
  extract:    'Pull audio track',
  separate:   'Vocals / music split',
  transcribe: 'Speech → text',
  translate:  'ZH → VI',
  tts:        'Text → speech',
  compose:    'Render video',
  banner:     'Thumbnails',
}

export const StepNode = memo(({ id, data, selected }: NodeProps<StepNodeType>) => {
  const { selectNode, jobCurrentStep, jobDoneSteps } = useFlowStore()
  const [hov, setHov] = useState(false)
  const color = COLOR_MAP[data.stepKey] ?? '#64748b'

  const isCurrent = jobCurrentStep === id
  const isDone    = jobDoneSteps?.includes(id) ?? false

  const borderColor = selected    ? color
    : isCurrent  ? color + '70'
    : isDone     ? '#10b98140'
    : hov        ? '#2a2a38' : '#1a1a22'

  const bg = selected  ? `${color}0e`
    : isCurrent ? '#14141c' : '#101014'

  return (
    <div
      onClick={() => selectNode(id)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{ width: 168, cursor: 'pointer', position: 'relative' }}
    >
      <Handle
        type="target" position={Position.Left}
        style={{
          background: isDone ? '#10b98120' : '#0c0c10',
          border: `2px solid ${isDone ? '#10b98170' : '#2a2a36'}`,
          width: 14, height: 14,
        }}
      />

      <div style={{
        border: `1px solid ${borderColor}`,
        background: bg,
        borderRadius: 8,
        padding: '0 18px 0 20px',
        height: 64,
        display: 'flex', alignItems: 'center', gap: 10,
        boxShadow: selected ? `0 0 0 3px ${color}15`
          : isCurrent ? `0 0 0 2px ${color}18` : 'none',
        transition: 'border-color 0.13s, box-shadow 0.13s, background 0.13s',
        userSelect: 'none',
      }}>
        {/* Color pip */}
        <div style={{
          width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
          background: isDone ? '#10b981' : isCurrent ? color : color + '60',
          boxShadow: isCurrent ? `0 0 6px ${color}80` : 'none',
          transition: 'background 0.2s, box-shadow 0.2s',
        }} />

        {/* Label + status */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12, fontWeight: 600, letterSpacing: '-0.01em',
            color: selected ? color : isCurrent ? '#d0d0e8' : isDone ? '#444454' : '#666676',
            transition: 'color 0.15s',
          }}>
            {data.label}
          </div>
          <div style={{ fontSize: 10, marginTop: 2, color: isCurrent ? color : isDone ? '#10b981' : '#252530' }}>
            {isCurrent ? '● running' : isDone ? '✓ done' : (DESC_MAP[data.stepKey] ?? '')}
          </div>
        </div>

        {/* Running badge */}
        {isCurrent && (
          <div style={{
            position: 'absolute', top: -6, right: -6,
            width: 13, height: 13, borderRadius: '50%',
            background: color, border: '2px solid #0b0b0d',
            animation: 'pulseDot 1.2s infinite',
          }} />
        )}
        {isDone && (
          <div style={{
            position: 'absolute', top: -6, right: -6,
            width: 13, height: 13, borderRadius: '50%',
            background: '#10b981', border: '2px solid #0b0b0d',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 7, color: '#fff', fontWeight: 800,
          }}>✓</div>
        )}
      </div>

      <Handle
        type="source" position={Position.Right}
        style={{
          background: hov ? color + '30' : '#0c0c10',
          border: `2px solid ${hov ? color : '#2a2a36'}`,
          width: 14, height: 14,
          transition: 'border-color 0.1s, background 0.1s',
        }}
      />
    </div>
  )
})

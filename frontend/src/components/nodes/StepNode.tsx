import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { useFlowStore, STEP_DEFS, type StepNodeData } from '../../stores/flowStore'

type StepNodeType = Node<StepNodeData, 'stepNode'>

const COLOR_MAP: Record<string, string> = Object.fromEntries(
  STEP_DEFS.map((s) => [s.key, s.color])
)

export const StepNode = memo(({ id, data, selected }: NodeProps<StepNodeType>) => {
  const selectNode = useFlowStore((s) => s.selectNode)
  const color = COLOR_MAP[data.stepKey] ?? '#64748b'

  return (
    <div
      onClick={() => selectNode(id)}
      className="cursor-pointer"
      style={{ width: 160 }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#475569' }} />

      <div
        style={{
          border: `2px solid ${selected ? color : '#334155'}`,
          background: selected ? `${color}22` : '#1e2433',
          borderRadius: 12,
          padding: '12px 16px',
          textAlign: 'center',
          transition: 'border-color 0.15s, background 0.15s',
          boxShadow: selected ? `0 0 0 2px ${color}44` : 'none',
        }}
      >
        <div style={{ fontSize: 28, marginBottom: 6 }}>{data.icon}</div>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{data.label}</div>
        <div
          style={{
            width: 8, height: 8, borderRadius: '50%',
            background: color, margin: '8px auto 0',
          }}
        />
      </div>

      <Handle type="source" position={Position.Right} style={{ background: '#475569' }} />
    </div>
  )
})

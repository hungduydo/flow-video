import { create } from 'zustand'
import type { Node, Edge } from '@xyflow/react'
import type { JobCreateRequest } from '../types'

export interface StepNodeData extends Record<string, unknown> {
  stepKey: string
  label: string
  icon: string
  config: Partial<JobCreateRequest>
}

interface FlowStore {
  nodes: Node<StepNodeData>[]
  edges: Edge[]
  selectedNodeId: string | null
  flowName: string
  flowSchedule: string | null
  flowEnabled: boolean
  setNodes: (nodes: Node<StepNodeData>[]) => void
  setEdges: (edges: Edge[]) => void
  selectNode: (id: string | null) => void
  updateNodeConfig: (nodeId: string, patch: Partial<JobCreateRequest>) => void
  setFlowMeta: (name: string, schedule: string | null, enabled: boolean) => void
  initFromDefinition: (def: JobCreateRequest) => void
  toDefinition: () => JobCreateRequest
}

// Pipeline step definitions
export const STEP_DEFS = [
  { key: 'download',   label: 'Download',     icon: '⬇️',  color: '#3b82f6' },
  { key: 'scenes',     label: 'Scene Cut',    icon: '🎬',  color: '#8b5cf6' },
  { key: 'extract',    label: 'Extract Audio', icon: '🎵', color: '#8b5cf6' },
  { key: 'separate',   label: 'Separate Audio',icon: '🎚️', color: '#8b5cf6' },
  { key: 'transcribe', label: 'Transcribe',   icon: '📝',  color: '#10b981' },
  { key: 'translate',  label: 'Translate',    icon: '🌐',  color: '#f59e0b' },
  { key: 'tts',        label: 'TTS',          icon: '🔊',  color: '#ef4444' },
  { key: 'compose',    label: 'Compose',      icon: '🎞️',  color: '#ec4899' },
  { key: 'banner',     label: 'Banner',       icon: '🖼️',  color: '#06b6d4' },
]

const NODE_WIDTH = 160
const NODE_GAP = 60

function buildNodes(def: JobCreateRequest): Node<StepNodeData>[] {
  return STEP_DEFS.map((step, i) => ({
    id: step.key,
    type: 'stepNode',
    position: { x: i * (NODE_WIDTH + NODE_GAP), y: 100 },
    data: {
      stepKey: step.key,
      label: step.label,
      icon: step.icon,
      config: extractStepConfig(step.key, def),
    },
    draggable: false,
  }))
}

function buildEdges(): Edge[] {
  return STEP_DEFS.slice(0, -1).map((step, i) => ({
    id: `e-${step.key}-${STEP_DEFS[i + 1].key}`,
    source: step.key,
    target: STEP_DEFS[i + 1].key,
    type: 'smoothstep',
    style: { stroke: '#475569', strokeWidth: 2 },
    animated: false,
  }))
}

function extractStepConfig(stepKey: string, def: JobCreateRequest): Partial<JobCreateRequest> {
  switch (stepKey) {
    case 'download':
      return { url: def.url, cookies_file: def.cookies_file, output_dir: def.output_dir }
    case 'transcribe':
      return { model: def.model, transcriber: def.transcriber }
    case 'translate':
      return { translator: def.translator }
    case 'tts':
      return { tts_provider: def.tts_provider }
    case 'compose':
      return { platform: def.platform, crf: def.crf, show_subtitle: def.show_subtitle, tiktok_crop_x: def.tiktok_crop_x }
    case 'banner':
      return {}
    default:
      return {}
  }
}

function mergeNodeConfigs(nodes: Node<StepNodeData>[]): JobCreateRequest {
  const merged: Partial<JobCreateRequest> = {}
  for (const node of nodes) {
    Object.assign(merged, node.data.config)
  }
  return {
    url: merged.url ?? '',
    cookies_file: merged.cookies_file ?? null,
    model: merged.model ?? 'large-v3',
    transcriber: merged.transcriber ?? 'whisper',
    translator: merged.translator ?? 'gemini',
    tts_provider: merged.tts_provider ?? 'edge_tts',
    platform: merged.platform ?? 'youtube',
    show_subtitle: merged.show_subtitle ?? true,
    crf: merged.crf ?? 23,
    tiktok_crop_x: merged.tiktok_crop_x ?? null,
    force: merged.force ?? false,
    output_dir: merged.output_dir ?? 'output',
  }
}

export const useFlowStore = create<FlowStore>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  flowName: 'New Flow',
  flowSchedule: null,
  flowEnabled: true,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  selectNode: (id) => set({ selectedNodeId: id }),

  updateNodeConfig: (nodeId, patch) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, config: { ...n.data.config, ...patch } } } : n
      ),
    })),

  setFlowMeta: (name, schedule, enabled) =>
    set({ flowName: name, flowSchedule: schedule, flowEnabled: enabled }),

  initFromDefinition: (def) =>
    set({
      nodes: buildNodes(def),
      edges: buildEdges(),
    }),

  toDefinition: () => mergeNodeConfigs(get().nodes),
}))

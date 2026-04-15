export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'
export type Platform = 'youtube' | 'tiktok' | 'both'
export type TranscriberProvider = 'whisper' | 'deepgram'
export type TranslatorProvider = 'gemini' | 'claude' | 'ollama_cloud'
export type TtsProvider = 'edge_tts' | 'elevenlabs'
export type WhisperModel = 'large-v3' | 'large-v2' | 'medium' | 'small' | 'base'

export interface JobCreateRequest {
  url: string
  cookies_file?: string | null
  model: WhisperModel
  transcriber: TranscriberProvider
  translator: TranslatorProvider
  tts_provider: TtsProvider
  platform: Platform
  show_subtitle: boolean
  crf: number
  tiktok_crop_x?: number | null
  from_step?: number | null
  force: boolean
  output_dir: string
}

export interface JobResponse {
  job_id: string
  status: JobStatus
  video_id?: string | null
  current_step?: number | string | null
  current_step_name?: string | null
  failed_step?: number | string | null
  failed_step_name?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
  output_files: string[]
  request: JobCreateRequest
}

export interface FlowResponse {
  id: string
  name: string
  definition: JobCreateRequest
  schedule?: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface FlowCreateRequest {
  name: string
  definition: JobCreateRequest
  schedule?: string | null
  enabled: boolean
}

export interface FlowUpdateRequest {
  name?: string
  definition?: JobCreateRequest
  schedule?: string | null
  enabled?: boolean
}

export const DEFAULT_DEFINITION: JobCreateRequest = {
  url: '',
  model: 'large-v3',
  transcriber: 'whisper',
  translator: 'gemini',
  tts_provider: 'edge_tts',
  platform: 'youtube',
  show_subtitle: true,
  crf: 23,
  force: false,
  output_dir: 'output',
}

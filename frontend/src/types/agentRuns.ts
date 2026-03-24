import type { UUID } from './common'

export interface CreateAgentRunRequest {
  platform: string
  region?: string | null
  category?: string | null
  keywords?: string[] | null
  price_min?: number | null
  price_max?: number | null
  target_languages?: string[]
  max_candidates?: number
}

export interface AgentRunResponse {
  run_id: UUID
  status: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface AgentRunStatusResponse {
  run_id: UUID
  status: string
  current_step?: string | null
  progress: {
    total_steps: number
    completed_steps: number
  }
  candidates_discovered: number
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface AgentRunResultsResponse {
  run_id: UUID
  status: string
  candidates: Array<{
    candidate_id: UUID
    title: string
    platform_price: number | null
    estimated_margin: number | null
    margin_percentage: number | null
    risk_decision: string | null
    risk_score: number | null
    listing_drafts: Array<{
      language: string
      title: string
      bullets: string[]
    }>
  }>
}

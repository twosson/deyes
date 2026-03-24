import type { UUID } from './common'

export interface StrategyRunListItem {
  run_id: UUID
  status: string
  source_platform: string
  region: string | null
  category: string | null
  keywords: string[] | null
  max_candidates: number
  current_step: string | null
  completed_steps: number
  total_steps: number
  candidates_discovered: number
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface ListStrategyRunsResponse {
  total: number
  runs: StrategyRunListItem[]
}

export interface AgentRunStep {
  id: UUID
  step_name: string
  agent_name: string
  status: string
  attempt: number
  error_message: string | null
  started_at: string
  completed_at: string | null
  latency_ms: number | null
}

export interface AgentRunStepsResponse {
  run_id: UUID
  steps: AgentRunStep[]
}

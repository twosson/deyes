import type { UUID } from './common'

export enum ExperimentStatus {
  DRAFT = 'draft',
  ACTIVE = 'active',
  COMPLETED = 'completed',
  ARCHIVED = 'archived',
}

export enum MetricGoal {
  CTR = 'ctr',
  CVR = 'cvr',
  ORDERS = 'orders',
  REVENUE = 'revenue',
  UNITS_SOLD = 'units_sold',
  ROAS = 'roas',
}

export interface Experiment {
  id: UUID
  candidate_product_id: UUID
  name: string
  status: ExperimentStatus
  target_platform?: string
  region?: string
  metric_goal: MetricGoal
  winner_variant_group?: string
  created_at: string
  updated_at: string
}

export interface VariantPerformance {
  variant_group: string
  asset_count: number
  impressions: number
  clicks: number
  orders: number
  units_sold: number
  revenue: number
  ctr: number
  cvr: number
  avg_order_value: number
}

export interface ExperimentSummary {
  experiment_id: UUID
  experiment_status: ExperimentStatus
  variants: VariantPerformance[]
  winner_variant_group?: string
  confidence_level?: number
}

export interface CreateExperimentRequest {
  candidate_product_id: UUID
  name: string
  metric_goal: MetricGoal
  target_platform?: string
  region?: string
}

export interface ListExperimentsResponse {
  total: number
  experiments: Experiment[]
}

import type { UUID } from './common'

export interface RecommendationScoreBreakdown {
  priority_component: number
  margin_component: number
  risk_component: number
  supplier_component: number
  total_score: number
}

export interface RecommendationItem {
  candidate_id: UUID
  title: string
  category: string | null
  source_platform: string
  platform_price: number | null
  recommendation_score: number
  recommendation_level: 'HIGH' | 'MEDIUM' | 'LOW'
  reasons: string[]
  score_breakdown: RecommendationScoreBreakdown
  priority_score: number | null
  margin_percentage: number | null
  risk_decision: string | null
  risk_score: number | null
  created_at: string
}

export interface ListRecommendationsResponse {
  items: RecommendationItem[]
  count: number
  filters: {
    category: string | null
    min_score: number
    risk_level: string | null
  }
}

export interface RecommendationComponent {
  name: string
  value: number
  weight: string
  description: string
}

export interface RecommendationScoreExplanation {
  total_score: number
  components: RecommendationComponent[]
}

export interface RecommendationDetail {
  score: number
  level: 'HIGH' | 'MEDIUM' | 'LOW'
  reasons: string[]
  score_breakdown: RecommendationScoreExplanation
}

export interface PricingSummary {
  margin_percentage: number | null
  profitability_decision: string | null
  recommended_price: number | null
}

export interface RiskSummary {
  score: number
  decision: string
  rule_hits: any[]
}

export interface BestSupplier {
  supplier_name: string
  supplier_price: number | null
  confidence_score: number | null
  moq: number | null
}

export interface CandidateRecommendation {
  candidate_id: UUID
  title: string
  category: string | null
  source_platform: string
  source_url: string | null
  platform_price: number | null
  sales_count: number | null
  rating: number | null
  recommendation: RecommendationDetail
  pricing_summary: PricingSummary | null
  risk_summary: RiskSummary | null
  best_supplier: BestSupplier | null
  normalized_attributes: Record<string, any>
  created_at: string
}

export interface ListRecommendationsParams {
  limit?: number
  category?: string
  min_score?: number
  risk_level?: 'pass' | 'review' | 'reject'
}

export interface RecommendationStatsOverview {
  total_recommendations: number
  average_score: number
  high_quality_count: number
  high_quality_percentage: number
  by_level: Record<string, number>
  by_category: Record<string, number>
  score_distribution: Array<{
    range: string
    count: number
  }>
  margin_vs_score: Array<{
    score: number
    margin: number
    category: string
  }>
}

export interface RecommendationTrendDataPoint {
  date: string
  count: number
  average_score: number
}

export interface RecommendationTrendsResponse {
  period: string
  days: number
  min_score: number
  data: RecommendationTrendDataPoint[]
}

export interface PlatformComparisonDataPoint {
  platform: string
  count: number
  average_score: number
  high_quality_count: number
  high_quality_percentage: number
}

export interface PlatformComparisonResponse {
  min_score: number
  data: PlatformComparisonDataPoint[]
}

export interface FeedbackStatsDataPoint {
  action: string
  count: number
}

export interface FeedbackStatsResponse {
  days: number
  total_feedback: number
  data: FeedbackStatsDataPoint[]
}


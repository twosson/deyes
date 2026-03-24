import type { UUID } from './common'

export interface CandidateProduct {
  id: UUID
  title: string
  source_platform: string
  platform_price: number | null
  estimated_margin: number | null
  margin_percentage: number | null
  risk_decision: string | null
  risk_score: number | null
  status: string
  created_at: string
}

export interface CandidateDetail {
  id: UUID
  strategy_run_id: UUID
  source_platform: string
  source_product_id: string
  source_url: string
  title: string
  raw_title: string
  category: string | null
  currency: string
  platform_price: number | null
  sales_count: number | null
  rating: number | null
  main_image_url: string | null
  status: string
  pricing_assessment: PricingAssessment | null
  risk_assessment: RiskAssessment | null
  supplier_matches: SupplierMatch[]
  listing_drafts: ListingDraft[]
  created_at: string
}

export interface PricingBreakdownExplanation {
  supplier_price: number
  shipping: number
  platform_commission: number
  payment_fee: number
  return_cost: number
}

export interface SupplierSelectionScoreBreakdown {
  price_component: number | null
  confidence_component: number | null
  moq_component: number | null
  identity_bonus: number | null
  alternative_sku_penalty: number | null
  price_gap_penalty: number | null
}

export interface SupplierSelectionIdentitySignals {
  is_factory_result: boolean
  is_super_factory: boolean
  verified_supplier: boolean
  alternative_sku: boolean
}

export interface RankedSupplierPath {
  rank: number | null
  supplier_match_id: UUID
  supplier_name: string | null
  supplier_sku: string | null
  supplier_price: number | null
  moq: number | null
  confidence_score: number | null
  usable_for_pricing: boolean
  rejection_reason: string | null
  score: number | null
  score_breakdown: SupplierSelectionScoreBreakdown
  identity_signals: SupplierSelectionIdentitySignals
}

export interface SupplierSelectionExplanation {
  competition_set_size: number
  considered_supplier_count: number
  selected_supplier: RankedSupplierPath | null
  ranked_supplier_paths: RankedSupplierPath[]
  selection_reason: string
}

export interface PricingExplanation {
  breakdown: PricingBreakdownExplanation
  total_cost: number
  revenue: number
  margin: number
  supplier_selection?: SupplierSelectionExplanation
}

export interface PricingAssessment {
  estimated_shipping_cost: number | null
  platform_commission_rate: number | null
  payment_fee_rate: number | null
  return_rate_assumption: number | null
  total_cost: number | null
  estimated_margin: number | null
  margin_percentage: number | null
  recommended_price: number | null
  profitability_decision: string | null
  explanation: PricingExplanation | null
}

export interface RiskAssessment {
  score: number
  decision: string
  rule_hits: string[]
  llm_notes: string | null
}

export interface SupplierMatch {
  id: UUID
  supplier_name: string
  supplier_url: string
  supplier_sku: string | null
  supplier_price: number | null
  moq: number | null
  confidence_score: number | null
  selected: boolean
}

export interface ListingDraft {
  id: UUID
  language: string
  title: string
  bullets: string[]
  description: string | null
  seo_keywords: string[]
  status: string
  prompt_version: string | null
}

export interface ListCandidatesResponse {
  items: CandidateProduct[]
}

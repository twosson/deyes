import { formatNumber } from './formatters'
import type { RankedSupplierPath } from '../types/candidates'

export interface SupplierScoreBreakdownItem {
  label: string
  value: number | null
}

export function getCheapestSupplierPrice(paths?: RankedSupplierPath[] | null): number | null {
  const prices = (paths ?? [])
    .filter((path) => path.usable_for_pricing && path.supplier_price != null)
    .map((path) => path.supplier_price as number)

  if (!prices.length) return null
  return Math.min(...prices)
}

export function supplierPricePremium(
  path: RankedSupplierPath | null | undefined,
  cheapestPrice: number | null,
): number | null {
  if (!path?.usable_for_pricing || path.supplier_price == null || cheapestPrice == null) {
    return null
  }
  if (cheapestPrice <= 0) return null

  const premium = ((path.supplier_price - cheapestPrice) / cheapestPrice) * 100
  return premium <= 0 ? 0 : premium
}

export function supplierPricePremiumLabel(
  path: RankedSupplierPath | null | undefined,
  cheapestPrice: number | null,
): string {
  const premium = supplierPricePremium(path, cheapestPrice)
  if (premium == null) return '--'
  if (premium === 0) return '最低价'
  return `${formatNumber(premium)}%`
}

export function supplierScoreColor(path?: RankedSupplierPath | null): string {
  const score = path?.score
  if (score == null) return 'default'
  if (score >= 0.75) return 'success'
  if (score >= 0.5) return 'processing'
  if (score >= 0.25) return 'warning'
  return 'default'
}

export function supplierScoreBreakdownItems(
  path?: RankedSupplierPath | null,
): SupplierScoreBreakdownItem[] {
  if (!path?.score_breakdown) return []

  const breakdown = path.score_breakdown
  return [
    { label: '价格', value: breakdown.price_component },
    { label: '置信', value: breakdown.confidence_component },
    { label: 'MOQ', value: breakdown.moq_component },
    { label: '身份', value: breakdown.identity_bonus },
    { label: '备选惩罚', value: breakdown.alternative_sku_penalty },
    { label: '价差惩罚', value: breakdown.price_gap_penalty },
  ]
}

export function supplierScoreBreakdownPreviewItems(
  path?: RankedSupplierPath | null,
  limit = 3,
): SupplierScoreBreakdownItem[] {
  return supplierScoreBreakdownItems(path).slice(0, limit)
}

export function supplierSelectionTag(path?: RankedSupplierPath | null): {
  label: string
  color: string
} {
  if (!path?.usable_for_pricing) return { label: '不可定价', color: 'default' }
  if (path.identity_signals.alternative_sku) return { label: '备选 SKU', color: 'orange' }
  if (path.identity_signals.is_factory_result || path.identity_signals.verified_supplier) {
    return { label: '优选路径', color: 'success' }
  }
  return { label: '参与比较', color: 'blue' }
}

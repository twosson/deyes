import { describe, expect, it } from 'vitest'

import {
  getCheapestSupplierPrice,
  supplierPricePremiumLabel,
  supplierScoreBreakdownPreviewItems,
  supplierScoreColor,
  supplierSelectionTag,
} from './supplierHelpers'
import type { RankedSupplierPath } from '../types/candidates'

function buildRankedSupplierPath(
  overrides: Partial<RankedSupplierPath> = {},
): RankedSupplierPath {
  return {
    rank: 1,
    supplier_match_id: '11111111-1111-1111-1111-111111111111',
    supplier_name: '测试供应商',
    supplier_sku: 'sku-001',
    supplier_price: 10,
    moq: 20,
    confidence_score: 0.9,
    usable_for_pricing: true,
    rejection_reason: null,
    score: 0.8,
    score_breakdown: {
      price_component: 0.4,
      confidence_component: 0.2,
      moq_component: 0.1,
      identity_bonus: 0.05,
      alternative_sku_penalty: 0.02,
      price_gap_penalty: 0.01,
    },
    identity_signals: {
      is_factory_result: false,
      is_super_factory: false,
      verified_supplier: false,
      alternative_sku: false,
    },
    ...overrides,
  }
}

describe('supplierHelpers', () => {
  it('finds the cheapest usable supplier price', () => {
    const cheapestPrice = getCheapestSupplierPrice([
      buildRankedSupplierPath({ supplier_match_id: '11111111-1111-1111-1111-111111111111', supplier_price: null }),
      buildRankedSupplierPath({ supplier_match_id: '22222222-2222-2222-2222-222222222222', usable_for_pricing: false, supplier_price: 6 }),
      buildRankedSupplierPath({ supplier_match_id: '33333333-3333-3333-3333-333333333333', supplier_price: 8.5 }),
      buildRankedSupplierPath({ supplier_match_id: '44444444-4444-4444-4444-444444444444', supplier_price: 9.2 }),
    ])

    expect(cheapestPrice).toBe(8.5)
  })

  it('labels the lowest price and formats positive premiums', () => {
    const cheapest = 10

    expect(
      supplierPricePremiumLabel(
        buildRankedSupplierPath({ supplier_price: 10 }),
        cheapest,
      ),
    ).toBe('最低价')

    expect(
      supplierPricePremiumLabel(
        buildRankedSupplierPath({ supplier_price: 10.5 }),
        cheapest,
      ),
    ).toBe('5%')
  })

  it('returns placeholder when premium cannot be computed', () => {
    expect(
      supplierPricePremiumLabel(
        buildRankedSupplierPath({ usable_for_pricing: false }),
        10,
      ),
    ).toBe('--')

    expect(
      supplierPricePremiumLabel(
        buildRankedSupplierPath({ supplier_price: null }),
        10,
      ),
    ).toBe('--')

    expect(
      supplierPricePremiumLabel(
        buildRankedSupplierPath(),
        null,
      ),
    ).toBe('--')
  })

  it('maps score ranges to tag colors', () => {
    expect(supplierScoreColor(buildRankedSupplierPath({ score: 0.8 }))).toBe('success')
    expect(supplierScoreColor(buildRankedSupplierPath({ score: 0.5 }))).toBe('processing')
    expect(supplierScoreColor(buildRankedSupplierPath({ score: 0.25 }))).toBe('warning')
    expect(supplierScoreColor(buildRankedSupplierPath({ score: 0.24 }))).toBe('default')
    expect(supplierScoreColor(buildRankedSupplierPath({ score: null }))).toBe('default')
  })

  it('returns the correct selection tag for supplier states', () => {
    expect(
      supplierSelectionTag(buildRankedSupplierPath({ usable_for_pricing: false })),
    ).toEqual({ label: '不可定价', color: 'default' })

    expect(
      supplierSelectionTag(
        buildRankedSupplierPath({
          identity_signals: {
            is_factory_result: false,
            is_super_factory: false,
            verified_supplier: false,
            alternative_sku: true,
          },
        }),
      ),
    ).toEqual({ label: '备选 SKU', color: 'orange' })

    expect(
      supplierSelectionTag(
        buildRankedSupplierPath({
          identity_signals: {
            is_factory_result: true,
            is_super_factory: false,
            verified_supplier: false,
            alternative_sku: false,
          },
        }),
      ),
    ).toEqual({ label: '优选路径', color: 'success' })

    expect(supplierSelectionTag(buildRankedSupplierPath())).toEqual({
      label: '参与比较',
      color: 'blue',
    })
  })

  it('returns only the preview subset of score breakdown items', () => {
    const previewItems = supplierScoreBreakdownPreviewItems(buildRankedSupplierPath())

    expect(previewItems).toHaveLength(3)
    expect(previewItems.map((item) => item.label)).toEqual(['价格', '置信', 'MOQ'])
  })
})

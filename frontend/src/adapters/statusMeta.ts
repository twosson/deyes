const normalizeKey = (value?: string | null) => value?.toLowerCase() ?? ''

export const lifecycleMeta: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending_review: { label: '待审核', color: 'gold' },
  approved: { label: '已审核', color: 'processing' },
  content_generating: { label: '内容生成中', color: 'purple' },
  ready_to_publish: { label: '待发布', color: 'cyan' },
  published: { label: '已发布', color: 'success' },
  archived: { label: '已归档', color: 'default' },
}

export const candidateStatusMeta: Record<string, { label: string; color: string }> = {
  discovered: { label: '已发现', color: 'default' },
  priced: { label: '已测算', color: 'processing' },
  risk_assessed: { label: '已风控', color: 'purple' },
  copy_generated: { label: '已生成文案', color: 'cyan' },
  rejected: { label: '已拒绝', color: 'error' },
}

export const riskDecisionMeta: Record<string, { label: string; color: string }> = {
  pass: { label: '通过', color: 'success' },
  review: { label: '复核', color: 'warning' },
  reject: { label: '拒绝', color: 'error' },
}

export const listingStatusMeta: Record<string, { label: string; color: string }> = {
  pending: { label: '待上架', color: 'gold' },
  publishing: { label: '上架中', color: 'processing' },
  active: { label: '已上架', color: 'success' },
  paused: { label: '已暂停', color: 'warning' },
  out_of_stock: { label: '缺货', color: 'orange' },
  rejected: { label: '被拒绝', color: 'error' },
  delisted: { label: '已下架', color: 'default' },
}

export const sourcePlatformLabel: Record<string, string> = {
  alibaba_1688: '1688',
  temu: 'Temu',
  aliexpress: 'AliExpress',
  amazon: 'Amazon',
  ozon: 'Ozon',
  rakuten: 'Rakuten',
  mercado_libre: 'Mercado Libre',
}

export const assetTypeLabel: Record<string, string> = {
  main_image: '主图',
  detail_image: '详情图',
  video: '视频',
  '3d_model': '3D模型',
  white_background: '白底图',
  lifestyle: '场景图',
}

export function getLifecycleMeta(status?: string | null) {
  return lifecycleMeta[normalizeKey(status)] ?? { label: status ?? '--', color: 'default' }
}

export function getCandidateStatusMeta(status?: string | null) {
  return candidateStatusMeta[normalizeKey(status)] ?? { label: status ?? '--', color: 'default' }
}

export function getRiskDecisionMeta(decision?: string | null) {
  return riskDecisionMeta[normalizeKey(decision)] ?? { label: decision ?? '--', color: 'default' }
}

export function getListingStatusMeta(status?: string | null) {
  return listingStatusMeta[normalizeKey(status)] ?? { label: status ?? '--', color: 'default' }
}

export function getSourcePlatformLabel(source?: string | null) {
  return sourcePlatformLabel[normalizeKey(source)] ?? source ?? '--'
}

export function getAssetTypeLabel(assetType?: string | null) {
  return assetTypeLabel[normalizeKey(assetType)] ?? assetType ?? '--'
}

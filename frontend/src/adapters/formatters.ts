import dayjs from 'dayjs'

export function formatDateTime(value?: string | null): string {
  if (!value) return '--'
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

export function formatCurrency(value?: number | null, currency = 'USD'): string {
  if (value === null || value === undefined) return '--'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return `${value.toFixed(1)}%`
}

export function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return new Intl.NumberFormat('zh-CN').format(value)
}

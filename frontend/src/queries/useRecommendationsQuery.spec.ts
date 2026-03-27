import { describe, expect, it } from 'vitest'

describe('recommendations api url building', () => {
  it('builds trends query params correctly', () => {
    const params = { period: 'week', days: 14, min_score: 70 }
    const searchParams = new URLSearchParams()
    if (params.period) searchParams.append('period', params.period)
    if (params.days) searchParams.append('days', params.days.toString())
    if (params.min_score !== undefined) searchParams.append('min_score', params.min_score.toString())

    const query = searchParams.toString()
    const url = query ? `/recommendations/stats/trends?${query}` : '/recommendations/stats/trends'

    expect(url).toBe('/recommendations/stats/trends?period=week&days=14&min_score=70')
  })

  it('builds by-platform query params correctly', () => {
    const params = { min_score: 65 }
    const searchParams = new URLSearchParams()
    if (params.min_score !== undefined) searchParams.append('min_score', params.min_score.toString())

    const query = searchParams.toString()
    const url = query
      ? `/recommendations/stats/by-platform?${query}`
      : '/recommendations/stats/by-platform'

    expect(url).toBe('/recommendations/stats/by-platform?min_score=65')
  })

  it('builds feedback query params correctly', () => {
    const params = { days: 90 }
    const searchParams = new URLSearchParams()
    if (params.days) searchParams.append('days', params.days.toString())

    const query = searchParams.toString()
    const url = query
      ? `/recommendations/stats/feedback?${query}`
      : '/recommendations/stats/feedback'

    expect(url).toBe('/recommendations/stats/feedback?days=90')
  })
})



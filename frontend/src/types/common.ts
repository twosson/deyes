export type UUID = string

export interface PaginationParams {
  limit?: number
  offset?: number
}

export interface PaginatedResponse<T> {
  total: number
  items: T[]
}

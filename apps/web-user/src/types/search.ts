export type BookSource = {
  title_ko?: string
  authors?: string[]
  publisher_name?: string
  issued_year?: number
  volume?: number
  edition_labels?: string[]
  [key: string]: unknown
}

export type BookHit = {
  doc_id?: string
  rank?: number
  score?: number
  source?: BookSource
  [key: string]: unknown
}

export type SearchResponse = {
  trace_id?: string
  request_id?: string
  took_ms?: number
  ranking_applied?: boolean
  strategy?: string
  hits?: BookHit[]
  debug?: Record<string, unknown>
  [key: string]: unknown
}

export type HitDebug = {
  lex_rank?: number
  vec_rank?: number
  rrf_score?: number
  ranking_score?: number
  [key: string]: unknown
}

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
  debug?: HitDebug
  lex_rank?: number
  vec_rank?: number
  rrf_score?: number
  ranking_score?: number
  [key: string]: unknown
}

export type SearchDebug = {
  stages?: { lexical?: boolean; vector?: boolean; rerank?: boolean }
  applied_fallback_id?: string
  query_text_source_used?: string
  [key: string]: unknown
}

export type SearchResponse = {
  version?: string
  trace_id?: string
  request_id?: string
  took_ms?: number
  timed_out?: boolean
  total?: number
  ranking_applied?: boolean
  strategy?: string
  hits?: BookHit[]
  debug?: SearchDebug
  [key: string]: unknown
}

export type Book = {
  docId: string
  titleKo: string | null
  authors: string[]
  publisherName: string | null
  issuedYear: number | null
  volume: number | null
  editionLabels: string[]
}

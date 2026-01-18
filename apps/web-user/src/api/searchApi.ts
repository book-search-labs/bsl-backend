import { fetchJson, HttpError } from './http'
import type { Book, BookHit, SearchResponse } from '../types/search'

type SearchOptions = {
  size?: number
  from?: number
  vector?: boolean
  debug?: boolean
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

function createId(prefix: string) {
  const suffix =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(16).slice(2)
  return `${prefix}_${suffix}`
}

function normalizeBook(hit: BookHit, fallbackDocId?: string): Book | null {
  const docId = hit.doc_id ?? fallbackDocId
  if (!docId) return null

  const source = hit.source ?? {}

  return {
    docId,
    titleKo: typeof source.title_ko === 'string' ? source.title_ko : null,
    authors: Array.isArray(source.authors) ? source.authors : [],
    publisherName: typeof source.publisher_name === 'string' ? source.publisher_name : null,
    issuedYear: typeof source.issued_year === 'number' ? source.issued_year : null,
    volume: typeof source.volume === 'number' ? source.volume : null,
    editionLabels: Array.isArray(source.edition_labels) ? source.edition_labels : [],
  }
}

export async function search(query: string, options: SearchOptions = {}): Promise<SearchResponse> {
  const trimmed = query.trim()
  const size = options.size ?? 10
  const from = options.from ?? 0
  const vectorEnabled = options.vector ?? true
  const debugEnabled = options.debug ?? false

  const payload = {
    query_context_v1_1: {
      meta: {
        schemaVersion: 'qc.v1.1',
        traceId: createId('trace_web_user'),
        requestId: createId('req_web_user'),
        tenantId: 'books',
        timestampMs: Date.now(),
        locale: 'ko-KR',
        timezone: 'Asia/Seoul',
      },
      query: {
        raw: query,
        norm: trimmed,
        final: trimmed,
      },
      retrievalHints: {
        queryTextSource: 'query.final',
        lexical: {
          enabled: true,
          topKHint: 50,
          operator: 'and',
          preferredLogicalFields: ['title_ko', 'author_ko'],
        },
        vector: {
          enabled: vectorEnabled,
          topKHint: 50,
          fusionHint: { method: 'rrf', k: 60 },
        },
        rerank: { enabled: false, topKHint: 10 },
        filters: [],
        fallbackPolicy: [],
      },
    },
    options: {
      size,
      from,
      debug: debugEnabled,
    },
  }

  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL ?? 'http://localhost:8080'
  const result = await fetchJson<SearchResponse>(joinUrl(searchBaseUrl, '/search'), {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  return result.data
}

export async function searchByDocId(docId: string): Promise<Book | null> {
  if (!docId) return null

  const payload = {
    query: { raw: docId },
    options: { size: 5, from: 0, enableVector: false },
  }

  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL ?? 'http://localhost:8080'

  try {
    const result = await fetchJson<SearchResponse>(joinUrl(searchBaseUrl, '/search'), {
      method: 'POST',
      body: JSON.stringify(payload),
    })

    const hits = Array.isArray(result.data?.hits) ? result.data.hits : []
    if (hits.length === 0) return null

    const exact = hits.find((hit) => hit.doc_id === docId)
    const candidate = exact ?? hits[0]

    return normalizeBook(candidate, docId)
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) {
      return null
    }
    throw error
  }
}

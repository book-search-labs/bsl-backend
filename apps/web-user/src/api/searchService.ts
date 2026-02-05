import { fetchJson } from './http'
import type { SearchResponse } from '../types/search'

export type SearchOptions = { size: number; from: number; debug?: boolean }

export type BookDetailResponse = {
  version?: string
  doc_id?: string
  source?: {
    title_ko?: string
    authors?: string[]
    publisher_name?: string
    issued_year?: number
    volume?: number
    edition_labels?: string[]
    [key: string]: unknown
  }
  trace_id?: string
  request_id?: string
  took_ms?: number
  [key: string]: unknown
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

function resolveSearchBaseUrl() {
  return (
    import.meta.env.VITE_SEARCH_SERVICE_BASE_URL ??
    import.meta.env.VITE_SEARCH_BASE_URL ??
    'http://localhost:8080'
  )
}

export async function postSearchWithQc(
  qc: unknown,
  options: SearchOptions,
  headers?: HeadersInit,
): Promise<SearchResponse> {
  const searchBaseUrl = resolveSearchBaseUrl()
  const payload = {
    query_context_v1_1: qc,
    options,
  }

  return fetchJson<SearchResponse>(joinUrl(searchBaseUrl, '/search'), {
    method: 'POST',
    headers,
    body: payload,
  })
}

export async function getBookByDocId(docId: string, headers?: HeadersInit): Promise<BookDetailResponse> {
  const searchBaseUrl = resolveSearchBaseUrl()
  const encodedId = encodeURIComponent(docId)
  return fetchJson<BookDetailResponse>(joinUrl(searchBaseUrl, `/books/${encodedId}`), {
    method: 'GET',
    headers,
  })
}

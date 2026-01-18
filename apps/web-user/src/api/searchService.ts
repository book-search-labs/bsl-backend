import { fetchJson } from './http'
import type { SearchResponse } from '../types/search'

export type SearchOptions = { size: number; from: number; debug?: boolean }

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

export async function postSearchWithQc(qc: unknown, options: SearchOptions): Promise<SearchResponse> {
  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL ?? 'http://localhost:8080'
  const payload = {
    query_context_v1_1: qc,
    options,
  }

  return fetchJson<SearchResponse>(joinUrl(searchBaseUrl, '/search'), {
    method: 'POST',
    body: payload,
  })
}

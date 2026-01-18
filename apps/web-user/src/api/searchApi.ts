import { fetchJson, HttpError } from './http'
import { postQueryContext } from './queryService'
import { postSearchWithQc, type SearchOptions } from './searchService'
import type { Book, BookHit, SearchResponse } from '../types/search'

type SearchRequestOptions = Partial<SearchOptions> & {
  vector?: boolean
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

function ensureRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
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

export async function search(query: string, options: SearchRequestOptions = {}): Promise<SearchResponse> {
  const size = options.size ?? 10
  const from = options.from ?? 0
  const vectorEnabled = options.vector ?? true
  const debugEnabled = options.debug ?? false

  const qc = await postQueryContext(query)
  let qcForSearch: unknown = qc

  if (!vectorEnabled && qc && typeof qc === 'object') {
    const qcRecord = ensureRecord(qc)
    const retrievalHints = ensureRecord(qcRecord.retrievalHints)
    const vector = ensureRecord(retrievalHints.vector)

    qcForSearch = {
      ...qcRecord,
      retrievalHints: {
        ...retrievalHints,
        vector: {
          ...vector,
          enabled: false,
        },
      },
    }
  }

  return postSearchWithQc(qcForSearch, { size, from, debug: debugEnabled })
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
      body: payload,
    })

    const hits = Array.isArray(result?.hits) ? result.hits : []
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

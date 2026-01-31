import { createRequestContext, resolveApiMode, resolveBffBaseUrl, routeRequest } from './client'
import { fetchJson, HttpError } from './http'
import { postQueryContext } from './queryService'
import { getBookByDocId, type BookDetailResponse, postSearchWithQc, type SearchOptions } from './searchService'
import type { Book, BookHit, SearchResponse } from '../types/search'

type SearchRequestOptions = Partial<SearchOptions> & {
  vector?: boolean
}

type BffSearchHit = {
  doc_id?: string
  score?: number
  title?: string
  authors?: string[]
  publisher?: string
  publication_year?: number
  [key: string]: unknown
}

type BffSearchResponse = {
  version?: string
  trace_id?: string
  request_id?: string
  imp_id?: string
  query_hash?: string
  took_ms?: number
  timed_out?: boolean
  total?: number
  hits?: BffSearchHit[]
  debug?: { query_dsl?: Record<string, unknown> }
  [key: string]: unknown
}

type SearchClickEvent = {
  imp_id: string
  doc_id: string
  position: number
  query_hash: string
  experiment_id?: string
  policy_id?: string
}

type SearchDwellEvent = SearchClickEvent & {
  dwell_ms: number
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

function mapBffSearchResponse(response: BffSearchResponse): SearchResponse {
  const hits = Array.isArray(response.hits)
    ? response.hits
        .map((hit) => {
          if (!hit) return null
          return {
            doc_id: hit.doc_id,
            score: hit.score,
            source: {
              title_ko: hit.title ?? null,
              authors: Array.isArray(hit.authors) ? hit.authors : [],
              publisher_name: hit.publisher ?? null,
              issued_year: hit.publication_year ?? null,
            },
          }
        })
        .filter(Boolean)
    : []

  return {
    version: response.version,
    trace_id: response.trace_id,
    request_id: response.request_id,
    imp_id: response.imp_id,
    query_hash: response.query_hash,
    took_ms: response.took_ms,
    timed_out: response.timed_out,
    total: response.total,
    hits: hits as BookHit[],
    debug: response.debug as SearchResponse['debug'],
  }
}

async function searchDirect(
  query: string,
  options: SearchRequestOptions,
  headers: HeadersInit,
): Promise<SearchResponse> {
  const size = options.size ?? 10
  const from = options.from ?? 0
  const vectorEnabled = options.vector ?? true
  const debugEnabled = options.debug ?? false

  const qc = await postQueryContext(query, headers)
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

  return postSearchWithQc(qcForSearch, { size, from, debug: debugEnabled }, headers)
}

async function searchViaBff(
  query: string,
  options: SearchRequestOptions,
  headers: HeadersInit,
): Promise<SearchResponse> {
  const size = options.size ?? 10
  const from = options.from ?? 0
  const vectorEnabled = options.vector ?? true

  const payload = {
    query: { raw: query },
    options: { size, from, enableVector: vectorEnabled },
  }

  const response = await fetchJson<BffSearchResponse>(joinUrl(resolveBffBaseUrl(), '/search'), {
    method: 'POST',
    headers,
    body: payload,
  })

  return mapBffSearchResponse(response)
}

export async function search(query: string, options: SearchRequestOptions = {}): Promise<SearchResponse> {
  const requestContext = createRequestContext()
  return routeRequest({
    route: 'search',
    mode: resolveApiMode(),
    requestContext,
    bff: (context) => searchViaBff(query, options, context.headers),
    direct: (context) => searchDirect(query, options, context.headers),
  })
}

export async function searchByDocId(docId: string): Promise<Book | null> {
  if (!docId) return null

  try {
    const requestContext = createRequestContext()
    const detail = await routeRequest<BookDetailResponse>({
      route: 'book_detail',
      mode: resolveApiMode(),
      requestContext,
      bff: (context) => {
        const encodedId = encodeURIComponent(docId)
        return fetchJson<BookDetailResponse>(joinUrl(resolveBffBaseUrl(), `/books/${encodedId}`), {
          method: 'GET',
          headers: context.headers,
        })
      },
      direct: (context) => getBookByDocId(docId, context.headers),
    })

    if (!detail?.source) return null
    return normalizeBook({ doc_id: detail.doc_id, source: detail.source }, docId)
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) {
      return null
    }
    throw error
  }
}

export async function postSearchClick(event: SearchClickEvent): Promise<void> {
  const requestContext = createRequestContext()
  await fetchJson(joinUrl(resolveBffBaseUrl(), '/search/click'), {
    method: 'POST',
    headers: requestContext.headers,
    body: event,
  })
}

export async function postSearchDwell(event: SearchDwellEvent): Promise<void> {
  const requestContext = createRequestContext()
  await fetchJson(joinUrl(resolveBffBaseUrl(), '/search/dwell'), {
    method: 'POST',
    headers: requestContext.headers,
    body: event,
  })
}

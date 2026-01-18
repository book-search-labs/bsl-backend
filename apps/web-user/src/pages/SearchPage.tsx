import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { fetchJson, HttpError } from '../api/http'
import type { BookHit, SearchResponse } from '../types/search'

const DEFAULT_SIZE = 10
const SIZE_OPTIONS = [5, 10, 20]

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

function buildSearchPayload(
  query: string,
  size: number,
  vectorEnabled: boolean,
  debugEnabled: boolean,
) {
  return {
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
        norm: query.trim(),
        final: query.trim(),
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
      from: 0,
      debug: debugEnabled,
    },
  }
}

function formatErrorBody(body: unknown) {
  if (!body) return ''
  if (typeof body === 'string') return body
  try {
    return JSON.stringify(body, null, 2)
  } catch {
    return String(body)
  }
}

export default function SearchPage() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') ?? ''
  const trimmedQuery = query.trim()

  const [vectorEnabled, setVectorEnabled] = useState(true)
  const [debugEnabled, setDebugEnabled] = useState(true)
  const [size, setSize] = useState(DEFAULT_SIZE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<HttpError | null>(null)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const requestCounter = useRef(0)

  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL ?? 'http://localhost:8080'

  const hits = useMemo<BookHit[]>(() => {
    return Array.isArray(response?.hits) ? response?.hits : []
  }, [response])

  const executeSearch = useCallback(async () => {
    if (!trimmedQuery) {
      requestCounter.current += 1
      setError(null)
      setResponse(null)
      setHasSearched(false)
      setLoading(false)
      return
    }

    const nextSize = SIZE_OPTIONS.includes(size) ? size : DEFAULT_SIZE
    const payload = buildSearchPayload(trimmedQuery, nextSize, vectorEnabled, debugEnabled)
    const requestId = requestCounter.current + 1
    requestCounter.current = requestId

    setLoading(true)
    setHasSearched(true)
    setError(null)
    setResponse(null)

    try {
      const result = await fetchJson<SearchResponse>(joinUrl(searchBaseUrl, '/search'), {
        method: 'POST',
        body: JSON.stringify(payload),
      })

      if (requestId !== requestCounter.current) return
      setResponse(result.data)
    } catch (err) {
      if (requestId !== requestCounter.current) return
      const safeError =
        err instanceof HttpError
          ? err
          : new HttpError('unexpected_error', { status: 0, statusText: 'unknown', body: err })
      setError(safeError)
    } finally {
      if (requestId === requestCounter.current) {
        setLoading(false)
      }
    }
  }, [trimmedQuery, size, vectorEnabled, debugEnabled, searchBaseUrl])

  useEffect(() => {
    executeSearch()
  }, [executeSearch])

  const debugJson = response ? JSON.stringify(response.debug ?? null, null, 2) : ''
  const responseJson = response ? JSON.stringify(response, null, 2) : ''

  if (!trimmedQuery) {
    return (
      <section className="page-section">
        <div className="container py-5">
          <div className="row">
            <div className="col-lg-7">
              <h1 className="page-title">Search</h1>
              <p className="page-lead">
                Type a query in the header search bar to discover books, authors, and editions.
              </p>
              <div className="placeholder-card empty-state">
                <div className="empty-title">No query yet</div>
                <div className="empty-copy">
                  We are ready when you are. Try searching for a favorite title.
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="d-flex flex-column gap-4">
          <div className="d-flex flex-column flex-lg-row align-items-lg-end justify-content-between gap-3">
            <div>
              <h1 className="page-title">Results for "{trimmedQuery}"</h1>
              <p className="page-lead">Search results from the Search Service.</p>
            </div>
            <div className="placeholder-card results-toolbar">
              <div className="d-flex flex-wrap align-items-center gap-3">
                <div className="form-check form-switch m-0">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id="vectorToggle"
                    checked={vectorEnabled}
                    onChange={(event) => setVectorEnabled(event.currentTarget.checked)}
                    disabled={loading}
                  />
                  <label className="form-check-label" htmlFor="vectorToggle">
                    Vector
                  </label>
                </div>
                <div className="form-check form-switch m-0">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id="debugToggle"
                    checked={debugEnabled}
                    onChange={(event) => setDebugEnabled(event.currentTarget.checked)}
                    disabled={loading}
                  />
                  <label className="form-check-label" htmlFor="debugToggle">
                    Debug
                  </label>
                </div>
                <div className="d-flex align-items-center gap-2">
                  <label htmlFor="sizeSelect" className="small text-uppercase">
                    Size
                  </label>
                  <select
                    id="sizeSelect"
                    className="form-select form-select-sm"
                    value={size}
                    onChange={(event) => setSize(Number(event.target.value))}
                    disabled={loading}
                  >
                    {SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  className="btn btn-primary btn-sm"
                  type="button"
                  onClick={executeSearch}
                  disabled={loading}
                >
                  {loading ? 'Running...' : 'Run'}
                </button>
              </div>
            </div>
          </div>

          {error ? (
            <div className="alert alert-danger error-banner" role="alert">
              <div className="fw-semibold">Search request failed</div>
              <div className="small">
                {error.status ? `HTTP ${error.status}` : 'Network error'} | {error.statusText}
              </div>
              {error.body ? (
                <pre className="error-body">{formatErrorBody(error.body)}</pre>
              ) : null}
            </div>
          ) : null}

          {loading ? (
            <div className="placeholder-card loading-state">
              <div className="spinner-border text-primary" role="status" aria-label="Loading">
                <span className="visually-hidden">Loading</span>
              </div>
              <div>Searching for matching books...</div>
            </div>
          ) : null}

          {!loading && !error && hasSearched && hits.length === 0 ? (
            <div className="placeholder-card empty-state">
              <div className="empty-title">No results found</div>
              <div className="empty-copy">
                Try a different spelling or remove a keyword to broaden the search.
              </div>
            </div>
          ) : null}

          {!loading && !error && hits.length > 0 ? (
            <div className="results-list">
              {hits.map((hit, index) => {
                const source = hit.source ?? {}
                const title = source.title_ko ?? 'Untitled'
                const authors = Array.isArray(source.authors) ? source.authors.join(', ') : '-'
                const publisher = source.publisher_name ?? '-'
                const issuedYear = source.issued_year ?? '-'
                const volume = source.volume ?? '-'
                const editions = Array.isArray(source.edition_labels)
                  ? source.edition_labels.join(', ')
                  : '-'
                const docId = hit.doc_id
                const docLink = docId ? `/book/${encodeURIComponent(docId)}` : null

                return (
                  <div key={docId ?? `${title}-${index}`} className="result-card">
                    <div className="result-header">
                      {docLink ? (
                        <Link className="result-title" to={docLink}>
                          {title}
                        </Link>
                      ) : (
                        <span className="result-title">{title}</span>
                      )}
                      <span className="result-rank">#{hit.rank ?? index + 1}</span>
                    </div>
                    <div className="result-meta">
                      {authors} | {publisher}
                    </div>
                    <div className="result-meta">
                      Year {issuedYear} | Volume {volume}
                    </div>
                    <div className="result-meta">Editions: {editions}</div>
                  </div>
                )
              })}
            </div>
          ) : null}

          {debugEnabled && response ? (
            <details className="debug-panel">
              <summary>Debug response payload</summary>
              <pre>{debugJson || '// debug is empty'}</pre>
              <details className="debug-panel nested">
                <summary>Full response JSON</summary>
                <pre>{responseJson}</pre>
              </details>
            </details>
          ) : null}
        </div>
      </div>
    </section>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { HttpError } from '../api/http'
import { search } from '../api/searchApi'
import type { BookHit, SearchResponse } from '../types/search'

const DEFAULT_SIZE = 10
const SIZE_MIN = 1
const SIZE_MAX = 50
const EXAMPLE_QUERIES = ['harry potter', 'sci-fi classics', 'korean fiction', 'history essays']

type ViewMode = 'card' | 'compact'

type ErrorMessage = {
  statusLine: string
  detail?: string
  code?: string
}

function clampSize(value: number) {
  if (!Number.isFinite(value)) return DEFAULT_SIZE
  return Math.min(SIZE_MAX, Math.max(SIZE_MIN, Math.round(value)))
}

function parseSizeParam(value: string | null) {
  if (!value) return DEFAULT_SIZE
  const parsed = Number(value)
  return clampSize(parsed)
}

function parseVectorParam(value: string | null) {
  if (!value) return true
  const normalized = value.toLowerCase()
  if (normalized === 'false' || normalized === '0' || normalized === 'no') return false
  if (normalized === 'true' || normalized === '1' || normalized === 'yes') return true
  return true
}

function formatError(error: HttpError): ErrorMessage {
  if (error.body && typeof error.body === 'object') {
    const body = error.body as { error?: { code?: string; message?: string } }
    if (body.error?.message) {
      return {
        statusLine: error.status
          ? `HTTP ${error.status} ${error.statusText}`
          : `Network error ${error.statusText}`,
        detail: body.error.message,
        code: body.error.code,
      }
    }
  }

  let detail: string | undefined
  if (error.body !== undefined && error.body !== null) {
    if (typeof error.body === 'string') {
      detail = error.body
    } else {
      try {
        detail = JSON.stringify(error.body, null, 2)
      } catch {
        detail = String(error.body)
      }
    }
  }

  return {
    statusLine: error.status
      ? `HTTP ${error.status} ${error.statusText}`
      : `Network error ${error.statusText}`,
    detail,
  }
}

function getHitDebug(hit: BookHit) {
  const direct = hit as BookHit & {
    lex_rank?: number
    vec_rank?: number
    rrf_score?: number
    ranking_score?: number
  }
  const debug = hit.debug as
    | {
        lex_rank?: number
        vec_rank?: number
        rrf_score?: number
        ranking_score?: number
      }
    | undefined

  return {
    lex_rank: direct.lex_rank ?? debug?.lex_rank,
    vec_rank: direct.vec_rank ?? debug?.vec_rank,
    rrf_score: direct.rrf_score ?? debug?.rrf_score,
    ranking_score: direct.ranking_score ?? debug?.ranking_score,
  }
}

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.get('q') ?? ''
  const trimmedQuery = query.trim()

  const sizeValue = parseSizeParam(searchParams.get('size'))
  const vectorEnabled = parseVectorParam(searchParams.get('vector'))

  const [searchInput, setSearchInput] = useState(query)
  const [debugEnabled, setDebugEnabled] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('card')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<HttpError | null>(null)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const requestCounter = useRef(0)

  const hits = useMemo<BookHit[]>(() => {
    return Array.isArray(response?.hits) ? response?.hits : []
  }, [response])

  useEffect(() => {
    setSearchInput(query)
  }, [query])

  useEffect(() => {
    if (!trimmedQuery) return

    const normalizedSize = String(sizeValue)
    const normalizedVector = vectorEnabled ? 'true' : 'false'
    const params = new URLSearchParams(searchParams)
    let updated = false

    if (params.get('q') !== trimmedQuery) {
      params.set('q', trimmedQuery)
      updated = true
    }

    if (params.get('size') !== normalizedSize) {
      params.set('size', normalizedSize)
      updated = true
    }

    if (params.get('vector') !== normalizedVector) {
      params.set('vector', normalizedVector)
      updated = true
    }

    if (updated) {
      setSearchParams(params, { replace: true })
    }
  }, [searchParams, setSearchParams, sizeValue, trimmedQuery, vectorEnabled])

  const executeSearch = useCallback(async () => {
    if (!trimmedQuery) {
      requestCounter.current += 1
      setLoading(false)
      setError(null)
      setResponse(null)
      setHasSearched(false)
      return
    }

    const requestId = requestCounter.current + 1
    requestCounter.current = requestId

    setLoading(true)
    setHasSearched(true)
    setError(null)
    setResponse(null)

    try {
      const result = await search(trimmedQuery, {
        size: sizeValue,
        vector: vectorEnabled,
        debug: debugEnabled,
      })

      if (requestId !== requestCounter.current) return
      setResponse(result)
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
  }, [debugEnabled, sizeValue, trimmedQuery, vectorEnabled])

  useEffect(() => {
    executeSearch()
  }, [executeSearch])

  const updateParams = useCallback(
    (updates: { q?: string; size?: number; vector?: boolean }) => {
      const params = new URLSearchParams(searchParams)

      if (updates.q !== undefined) {
        if (updates.q) {
          params.set('q', updates.q)
        } else {
          params.delete('q')
        }
      }

      if (updates.size !== undefined) {
        params.set('size', String(clampSize(updates.size)))
      }

      if (updates.vector !== undefined) {
        params.set('vector', updates.vector ? 'true' : 'false')
      }

      setSearchParams(params)
    },
    [searchParams, setSearchParams],
  )

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextQuery = searchInput.trim()

    updateParams({
      q: nextQuery,
      size: sizeValue,
      vector: vectorEnabled,
    })
  }

  const handleSizeChange = (event: ChangeEvent<HTMLInputElement>) => {
    const rawValue = Number(event.target.value)
    if (!Number.isFinite(rawValue)) return
    updateParams({ size: clampSize(rawValue) })
  }

  const handleVectorToggle = (event: ChangeEvent<HTMLInputElement>) => {
    updateParams({ vector: event.currentTarget.checked })
  }

  const handleExampleClick = (value: string) => {
    updateParams({ q: value, size: sizeValue, vector: vectorEnabled })
  }

  const handleSelectHit = useCallback(
    (hit: BookHit) => {
      if (!hit.doc_id) return

      const debug = getHitDebug(hit)
      const payload = {
        doc_id: hit.doc_id,
        source: hit.source ?? null,
        debug,
        fromQuery: {
          q: trimmedQuery,
          size: sizeValue,
          vector: vectorEnabled,
        },
        ts: Date.now(),
      }

      try {
        sessionStorage.setItem(`bsl:lastHit:${hit.doc_id}`, JSON.stringify(payload))
      } catch {
        // Ignore storage failures
      }
    },
    [sizeValue, trimmedQuery, vectorEnabled],
  )

  const debugSummary = response?.debug as
    | {
        stages?: { lexical?: boolean; vector?: boolean; rerank?: boolean }
        applied_fallback_id?: string
        query_text_source_used?: string
      }
    | undefined

  const viewLabel = viewMode === 'card' ? 'Card view' : 'Compact view'

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="search-panel">
          <div>
            <h1 className="page-title">Search</h1>
            <p className="page-lead">Find books, editions, and authors across the catalog.</p>
          </div>
          <form className="search-form-inline" onSubmit={handleSubmit}>
            <input
              className="form-control form-control-lg search-input"
              type="search"
              placeholder="Search titles, authors, or series"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <button className="btn btn-primary btn-lg" type="submit">
              Search
            </button>
          </form>
        </div>

        {!trimmedQuery ? (
          <div className="placeholder-card empty-state mt-4">
            <div className="empty-title">Start with a query</div>
            <div className="empty-copy">Try one of these suggestions.</div>
            <div className="example-list">
              {EXAMPLE_QUERIES.map((example) => (
                <button
                  key={example}
                  type="button"
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => handleExampleClick(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="results-shell">
            <div className="results-header">
              <div>
                <h2 className="section-title">Results for "{trimmedQuery}"</h2>
                <div className="text-muted small">Size {sizeValue} | Vector {String(vectorEnabled)}</div>
              </div>
              <div className="results-toolbar">
                <div className="form-check form-switch m-0">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id="vectorToggle"
                    checked={vectorEnabled}
                    onChange={handleVectorToggle}
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
                <div className="size-control">
                  <label htmlFor="sizeInput" className="small text-uppercase">
                    Size
                  </label>
                  <input
                    id="sizeInput"
                    className="form-control form-control-sm"
                    type="number"
                    min={SIZE_MIN}
                    max={SIZE_MAX}
                    value={sizeValue}
                    onChange={handleSizeChange}
                    disabled={loading}
                  />
                </div>
                <div className="btn-group view-toggle" role="group" aria-label="Result view">
                  <button
                    type="button"
                    className={`btn btn-outline-dark btn-sm ${viewMode === 'card' ? 'active' : ''}`}
                    onClick={() => setViewMode('card')}
                  >
                    Cards
                  </button>
                  <button
                    type="button"
                    className={`btn btn-outline-dark btn-sm ${viewMode === 'compact' ? 'active' : ''}`}
                    onClick={() => setViewMode('compact')}
                  >
                    Compact
                  </button>
                </div>
                <button
                  className="btn btn-outline-secondary btn-sm"
                  type="button"
                  onClick={executeSearch}
                  disabled={loading}
                >
                  {loading ? 'Running...' : 'Run'}
                </button>
              </div>
            </div>

            {debugEnabled && response ? (
              <div className="placeholder-card debug-summary">
                <div className="debug-title">Debug summary</div>
                <div className="debug-grid">
                  <div>
                    <div className="debug-label">strategy</div>
                    <div className="debug-value">{response.strategy ?? '-'}</div>
                  </div>
                  <div>
                    <div className="debug-label">took_ms</div>
                    <div className="debug-value">{response.took_ms ?? '-'}</div>
                  </div>
                  <div>
                    <div className="debug-label">ranking_applied</div>
                    <div className="debug-value">{String(response.ranking_applied ?? '-')}</div>
                  </div>
                  <div>
                    <div className="debug-label">debug.stages</div>
                    <div className="debug-value">
                      {debugSummary?.stages
                        ? `lexical=${String(debugSummary.stages.lexical)} | vector=${String(
                            debugSummary.stages.vector,
                          )} | rerank=${String(debugSummary.stages.rerank)}`
                        : '-'}
                    </div>
                  </div>
                  <div>
                    <div className="debug-label">debug.applied_fallback_id</div>
                    <div className="debug-value">{debugSummary?.applied_fallback_id ?? '-'}</div>
                  </div>
                  <div>
                    <div className="debug-label">debug.query_text_source_used</div>
                    <div className="debug-value">{debugSummary?.query_text_source_used ?? '-'}</div>
                  </div>
                </div>
              </div>
            ) : null}

            {error ? (
              <div className="alert alert-danger error-banner" role="alert">
                {(() => {
                  const message = formatError(error)
                  return (
                    <>
                      <div className="fw-semibold">Search request failed</div>
                      <div className="small">
                        {message.statusLine}
                        {message.code ? ` | ${message.code}` : ''}
                      </div>
                      {message.detail ? <pre className="error-body">{message.detail}</pre> : null}
                    </>
                  )
                })()}
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
                  Try simplifying the query or check spelling for better matches.
                </div>
                <div className="example-list">
                  {EXAMPLE_QUERIES.map((example) => (
                    <button
                      key={example}
                      type="button"
                      className="btn btn-outline-secondary btn-sm"
                      onClick={() => handleExampleClick(example)}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {!loading && !error && hits.length > 0 ? (
              <div className={`results-list ${viewMode}-view`} aria-label={viewLabel}>
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
                  const score = typeof hit.score === 'number' ? hit.score : null
                  const docId = hit.doc_id
                  const docLink = docId ? `/book/${encodeURIComponent(docId)}?from=search` : null
                  const debug = getHitDebug(hit)
                  const debugEntries = Object.entries(debug).filter(([, value]) => value !== undefined)

                  return (
                    <div
                      key={docId ?? `${title}-${index}`}
                      className={viewMode === 'card' ? 'result-card' : 'result-row'}
                    >
                      <div className="result-header">
                        {docLink ? (
                          <Link
                            className="result-title"
                            to={docLink}
                            onClick={() => handleSelectHit(hit)}
                          >
                            {title}
                          </Link>
                        ) : (
                          <span className="result-title">{title}</span>
                        )}
                        <div className="result-badges">
                          <span className="score-badge">Score {score?.toFixed(3) ?? '-'}</span>
                          <span className="result-rank">#{hit.rank ?? index + 1}</span>
                        </div>
                      </div>
                      <div className="result-meta">
                        {authors} | {publisher}
                      </div>
                      <div className="result-meta">
                        Year {issuedYear} | Volume {volume}
                      </div>
                      <div className="result-meta">Editions: {editions}</div>
                      {debugEnabled && debugEntries.length > 0 ? (
                        <div className="result-debug">
                          {debugEntries.map(([key, value]) => (
                            <span key={key}>
                              {key}: {String(value)}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {docLink ? (
                        <div className="result-actions">
                          <Link
                            to={docLink}
                            className="btn btn-outline-dark btn-sm"
                            onClick={() => handleSelectHit(hit)}
                          >
                            View detail
                          </Link>
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </section>
  )
}

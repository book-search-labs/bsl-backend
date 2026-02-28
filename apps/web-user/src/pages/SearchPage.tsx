import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { Link, useOutletContext, useSearchParams } from 'react-router-dom'

import { postSearchClick, search } from '../api/searchApi'
import { HttpError } from '../api/http'
import type { KdcCategoryNode } from '../api/categories'
import BookCover from '../components/books/BookCover'
import type { BookHit, SearchResponse } from '../types/search'
import { collectKdcDescendantCodes, flattenKdcCategories, getTopLevelKdc } from '../utils/kdc'

const DEFAULT_SIZE = 10
const SIZE_MIN = 1
const SIZE_MAX = 50
const PAGE_WINDOW_SIZE = 3
const EXAMPLE_QUERIES = ['베스트셀러', '에세이', '자기계발', '한강', '어린이 그림책']
const REFINE_TAGS = ['세트', '양장본', '에디션', '개정판', '작가 인터뷰']
const CATEGORY_QUICK = ['문학', '경제 경영', '자기계발', '어린이', '외국어', '취미']
const EXPLICIT_FILTER_FIELDS = [
  { key: 'author', label: '저자' },
  { key: 'title', label: '제목' },
  { key: 'isbn', label: 'ISBN' },
  { key: 'publisher', label: '출판사' },
  { key: 'series', label: '시리즈' },
] as const

type ExplicitFilterKey = (typeof EXPLICIT_FILTER_FIELDS)[number]['key']
type AdvancedFilters = Record<ExplicitFilterKey, string>

function explicitPattern() {
  return /(author|title|isbn|publisher|series):(\"[^\"]+\"|\\S+)/gi
}

type ViewMode = 'card' | 'compact'

type ErrorMessage = {
  stage?: string
  statusLine: string
  detail?: string
  code?: string
}

type AppShellContext = {
  kdcCategories: KdcCategoryNode[]
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

function parsePageParam(value: string | null) {
  if (!value) return 1
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 1
  return Math.max(1, Math.floor(parsed))
}

function emptyAdvancedFilters(): AdvancedFilters {
  return {
    author: '',
    title: '',
    isbn: '',
    publisher: '',
    series: '',
  }
}

function hasAdvancedFilters(filters: AdvancedFilters) {
  return Object.values(filters).some((value) => value.trim().length > 0)
}

function stripExplicitSyntax(query: string) {
  return query.replace(explicitPattern(), ' ').replace(/\\s+/g, ' ').trim()
}

function composeQueryWithAdvancedFilters(query: string, filters: AdvancedFilters) {
  if (!hasAdvancedFilters(filters)) {
    return query.trim()
  }
  const base = stripExplicitSyntax(query)
  const tokens = EXPLICIT_FILTER_FIELDS.flatMap(({ key }) => {
    const value = filters[key].trim()
    return value.length > 0 ? [`${key}:${value}`] : []
  })
  return [base, ...tokens].join(' ').trim()
}

function extractAdvancedFilters(query: string): AdvancedFilters {
  const filters = emptyAdvancedFilters()
  const matches = query.matchAll(explicitPattern())
  for (const match of matches) {
    const key = match[1]?.toLowerCase() as ExplicitFilterKey | undefined
    const value = match[2]?.replace(/^\"|\"$/g, '').trim() ?? ''
    if (!key || !(key in filters) || !value) continue
    filters[key] = value
  }
  return filters
}

function formatError(error: HttpError, stage?: string): ErrorMessage {
  if (error.body && typeof error.body === 'object') {
    const body = error.body as { error?: { code?: string; message?: string } }
    if (body.error?.message) {
      return {
        stage,
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
    stage,
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
  const { kdcCategories } = useOutletContext<AppShellContext>()
  const query = searchParams.get('q') ?? ''
  const kdcCode = (searchParams.get('kdc') ?? '').trim()
  const relatedDocId = (searchParams.get('related') ?? '').trim()
  const relatedTitle = (searchParams.get('related_title') ?? '').trim()
  const hasRelatedSeed = relatedDocId.length > 0 || relatedTitle.length > 0
  const trimmedQuery = query.trim()

  const sizeValue = parseSizeParam(searchParams.get('size'))
  const vectorEnabled = parseVectorParam(searchParams.get('vector'))
  const pageValue = parsePageParam(searchParams.get('page'))
  const fromValue = (pageValue - 1) * sizeValue

  const [searchInput, setSearchInput] = useState(query)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [advancedFilters, setAdvancedFilters] = useState<AdvancedFilters>(emptyAdvancedFilters)
  const [debugEnabled, setDebugEnabled] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('card')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ErrorMessage | null>(null)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const requestCounter = useRef(0)

  const topCategories = useMemo(() => getTopLevelKdc(kdcCategories), [kdcCategories])
  const categoryIndex = useMemo(() => flattenKdcCategories(kdcCategories), [kdcCategories])
  const selectedCategory = kdcCode ? categoryIndex.get(kdcCode) : undefined
  const selectedCategoryCodes = useMemo(
    () => collectKdcDescendantCodes(selectedCategory),
    [selectedCategory],
  )
  const categoryQuick = useMemo(() => {
    if (topCategories.length > 0) {
      return topCategories.map((node) => ({ label: node.name, code: node.code }))
    }
    return CATEGORY_QUICK.map((label) => ({ label, query: label }))
  }, [topCategories])

  const hits = useMemo<BookHit[]>(() => {
    const values = Array.isArray(response?.hits) ? response.hits : []
    if (!hasRelatedSeed) return values

    const normalizedRelatedDocId = relatedDocId.toLowerCase()
    const normalizedRelatedTitle = relatedTitle.replace(/\s+/g, '').toLowerCase()

    return values.filter((hit) => {
      const currentDocId = String(hit.doc_id ?? '').trim().toLowerCase()
      if (normalizedRelatedDocId && currentDocId === normalizedRelatedDocId) {
        return false
      }

      if (normalizedRelatedTitle) {
        const currentTitle = String(hit.source?.title_ko ?? '').replace(/\s+/g, '').toLowerCase()
        if (currentTitle && currentTitle === normalizedRelatedTitle) {
          return false
        }
      }

      return true
    })
  }, [hasRelatedSeed, relatedDocId, relatedTitle, response])

  useEffect(() => {
    setSearchInput(query)
    setAdvancedFilters(extractAdvancedFilters(query))
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
    const hasCategoryFilter = selectedCategoryCodes.length > 0
    const shouldSearch = trimmedQuery.length > 0 || kdcCode.length > 0

    if (!shouldSearch) {
      requestCounter.current += 1
      setLoading(false)
      setError(null)
      setResponse(null)
      setHasSearched(false)
      return
    }

    if (kdcCode && kdcCategories.length === 0) {
      setLoading(true)
      setHasSearched(true)
      setError(null)
      setResponse(null)
      return
    }

    if (kdcCode && kdcCategories.length > 0 && !selectedCategory) {
      requestCounter.current += 1
      setLoading(false)
      setHasSearched(false)
      setError({
        stage: 'category',
        statusLine: 'Invalid category',
        detail: '선택한 카테고리를 찾을 수 없습니다.',
      })
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
        from: fromValue,
        debug: debugEnabled,
        vector: trimmedQuery.length > 0 ? (hasRelatedSeed ? true : vectorEnabled) : false,
        filters: hasCategoryFilter
          ? [
              {
                and: [
                  {
                    scope: 'CATALOG',
                    logicalField: 'kdc_path_codes',
                    op: 'eq',
                    value: selectedCategoryCodes,
                  },
                ],
              },
            ]
          : undefined,
      })

      if (requestId !== requestCounter.current) return
      setResponse(result)
    } catch (err) {
      if (requestId !== requestCounter.current) return
      const safeError =
        err instanceof HttpError
          ? err
          : new HttpError('unexpected_error', { status: 0, statusText: 'unknown', body: err })
      setError(formatError(safeError, 'search'))
    } finally {
      if (requestId === requestCounter.current) {
        setLoading(false)
      }
    }
  }, [
    debugEnabled,
    kdcCategories.length,
    kdcCode,
    selectedCategory,
    selectedCategoryCodes,
    sizeValue,
    fromValue,
    trimmedQuery,
    hasRelatedSeed,
    vectorEnabled,
  ])

  useEffect(() => {
    executeSearch()
  }, [executeSearch])

  const updateParams = useCallback(
    (updates: {
      q?: string
      size?: number
      vector?: boolean
      kdc?: string
      page?: number
      related?: string
      relatedTitle?: string
    }) => {
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

      if (updates.kdc !== undefined) {
        if (updates.kdc) {
          params.set('kdc', updates.kdc)
        } else {
          params.delete('kdc')
        }
      }

      if (updates.page !== undefined) {
        const nextPage = Math.max(1, Math.floor(updates.page))
        params.set('page', String(nextPage))
      }

      if (updates.related !== undefined) {
        if (updates.related) {
          params.set('related', updates.related)
        } else {
          params.delete('related')
        }
      }

      if (updates.relatedTitle !== undefined) {
        if (updates.relatedTitle) {
          params.set('related_title', updates.relatedTitle)
        } else {
          params.delete('related_title')
        }
      }

      setSearchParams(params)
    },
    [searchParams, setSearchParams],
  )

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextQuery = composeQueryWithAdvancedFilters(searchInput, advancedFilters)

    updateParams({
      q: nextQuery,
      size: sizeValue,
      vector: vectorEnabled,
      kdc: nextQuery.trim().length > 0 ? '' : undefined,
      page: 1,
      related: '',
      relatedTitle: '',
    })
  }

  const handleSizeChange = (event: ChangeEvent<HTMLInputElement>) => {
    const rawValue = Number(event.target.value)
    if (!Number.isFinite(rawValue)) return
    updateParams({ size: clampSize(rawValue), page: 1 })
  }

  const handleVectorToggle = (event: ChangeEvent<HTMLInputElement>) => {
    updateParams({ vector: event.currentTarget.checked })
  }

  const handleExampleClick = (value: string) => {
    setAdvancedFilters(emptyAdvancedFilters())
    updateParams({ q: value, size: sizeValue, vector: vectorEnabled, kdc: '', page: 1, related: '', relatedTitle: '' })
  }

  const handleRefine = (value: string) => {
    const base = trimmedQuery || searchInput.trim()
    const next = base ? `${base} ${value}` : value
    updateParams({
      q: next,
      size: sizeValue,
      vector: vectorEnabled,
      kdc: next.trim().length > 0 ? '' : undefined,
      page: 1,
      related: '',
      relatedTitle: '',
    })
  }

  const handleFilterChip = (key: ExplicitFilterKey) => {
    const token = `${key}:`
    if (searchInput.includes(token)) {
      setShowAdvanced(true)
      return
    }
    const next = `${searchInput.trim()} ${token}`.trim()
    setSearchInput(next.length > 0 ? `${next} ` : token)
    setShowAdvanced(true)
  }

  const handleAdvancedFilterChange = (key: ExplicitFilterKey, value: string) => {
    setAdvancedFilters((prev) => ({
      ...prev,
      [key]: value,
    }))
  }

  const applyAdvancedFilters = () => {
    const nextQuery = composeQueryWithAdvancedFilters(searchInput, advancedFilters)
    updateParams({
      q: nextQuery,
      size: sizeValue,
      vector: vectorEnabled,
      kdc: nextQuery.trim().length > 0 ? '' : undefined,
      page: 1,
      related: '',
      relatedTitle: '',
    })
  }

  const clearAdvancedFilters = () => {
    setAdvancedFilters(emptyAdvancedFilters())
    updateParams({
      q: stripExplicitSyntax(searchInput),
      size: sizeValue,
      vector: vectorEnabled,
      page: 1,
      related: '',
      relatedTitle: '',
    })
  }

  const handleCategoryClick = (code?: string) => {
    if (!code) return
    setAdvancedFilters(emptyAdvancedFilters())
    updateParams({ kdc: code, q: '', size: sizeValue, vector: vectorEnabled, page: 1, related: '', relatedTitle: '' })
  }

  const handleSimilarBooks = useCallback(
    (title: string, docId?: string) => {
      const nextQuery = title.trim()
      if (!nextQuery) return
      updateParams({
        q: nextQuery,
        size: Math.max(sizeValue, 20),
        vector: true,
        kdc: '',
        page: 1,
        related: docId ?? '',
        relatedTitle: nextQuery,
      })
    },
    [sizeValue, updateParams],
  )

  const handleSelectHit = useCallback(
    (hit: BookHit, position: number) => {
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
        imp_id: response?.imp_id ?? undefined,
        query_hash: response?.query_hash ?? undefined,
        position,
        ts: Date.now(),
      }

      try {
        sessionStorage.setItem(`bsl:lastHit:${hit.doc_id}`, JSON.stringify(payload))
      } catch {
        // Ignore storage failures
      }

      if (response?.imp_id && response?.query_hash) {
        postSearchClick({
          imp_id: response.imp_id,
          doc_id: hit.doc_id,
          position,
          query_hash: response.query_hash,
        }).catch(() => {
          // Ignore event failures
        })
      }
    },
    [response?.imp_id, response?.query_hash, sizeValue, trimmedQuery, vectorEnabled],
  )

  const debugSummary = response?.debug as
    | {
        stages?: { lexical?: boolean; vector?: boolean; rerank?: boolean }
        applied_fallback_id?: string
        query_text_source_used?: string
      }
    | undefined

  const traceId = response?.trace_id ?? '-'
  const requestId = response?.request_id ?? '-'

  const viewLabel = viewMode === 'card' ? 'Grid view' : 'List view'
  const totalCount = response?.total ?? hits.length
  const totalPages = Math.max(1, Math.ceil(totalCount / sizeValue))
  const hasPrevPage = pageValue > 1
  const hasNextPage = pageValue < totalPages
  const pageWindowStart = Math.floor((pageValue - 1) / PAGE_WINDOW_SIZE) * PAGE_WINDOW_SIZE + 1
  const pageStart = Math.max(1, pageWindowStart)
  const pageEnd = Math.min(totalPages, pageStart + PAGE_WINDOW_SIZE - 1)
  const pageNumbers = Array.from({ length: pageEnd - pageStart + 1 }, (_, idx) => pageStart + idx)
  const currentStart = totalCount > 0 ? fromValue + 1 : 0
  const currentEnd = totalCount > 0 ? fromValue + hits.length : 0
  const displayQuery = stripExplicitSyntax(trimmedQuery) || trimmedQuery
  const resultsTitle = trimmedQuery
    ? hasRelatedSeed
      ? `"${displayQuery}" 비슷한 책`
      : `"${displayQuery}" 검색 결과`
    : selectedCategory
      ? `${selectedCategory.name} 카테고리`
      : '검색 결과'

  return (
    <section className="page-section">
      <div className="container py-5 search-page">
        <div className="search-hero">
          <div>
            <h1 className="page-title">도서 검색</h1>
            <p className="page-lead">검색 결과와 추천을 한 번에 확인하세요.</p>
          </div>
          <div className="search-hero-actions">
            <Link to="/chat" className="btn btn-outline-secondary btn-sm">
              책봇에 문의
            </Link>
          </div>
        </div>

        <form className="search-form-inline search-form--page" onSubmit={handleSubmit}>
          <input
            className="form-control form-control-lg search-input"
            type="search"
            placeholder="도서, 저자, 키워드를 입력하세요"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
          <button className="btn btn-primary btn-lg" type="submit">
            검색
          </button>
        </form>

        <div className="explicit-filter-bar mt-3">
          <div className="filter-chip-row">
            {EXPLICIT_FILTER_FIELDS.map((field) => (
              <button
                key={field.key}
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={() => handleFilterChip(field.key)}
              >
                {field.label}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-outline-dark btn-sm"
              onClick={() => setShowAdvanced((prev) => !prev)}
            >
              {showAdvanced ? '고급 필터 닫기' : '고급 검색'}
            </button>
          </div>
          {showAdvanced && (
            <div className="advanced-filter-panel mt-3">
              <div className="row g-2">
                {EXPLICIT_FILTER_FIELDS.map((field) => (
                  <div key={field.key} className="col-12 col-md-6 col-xl-4">
                    <label className="form-label small text-muted mb-1">{field.label}</label>
                    <input
                      className="form-control form-control-sm"
                      type="text"
                      value={advancedFilters[field.key]}
                      onChange={(event) => handleAdvancedFilterChange(field.key, event.target.value)}
                      placeholder={`${field.key}:...`}
                    />
                  </div>
                ))}
              </div>
              <div className="d-flex gap-2 mt-3">
                <button type="button" className="btn btn-sm btn-dark" onClick={applyAdvancedFilters}>
                  필터 적용
                </button>
                <button type="button" className="btn btn-sm btn-outline-secondary" onClick={clearAdvancedFilters}>
                  필터 초기화
                </button>
              </div>
            </div>
          )}
        </div>

        {!trimmedQuery && !kdcCode ? (
          <div className="placeholder-card empty-state mt-4">
            <div className="empty-title">검색어를 입력해주세요</div>
            <div className="empty-copy">아래 추천 검색어로 시작해보세요.</div>
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
          <div className="search-layout">
            <aside className="search-sidebar">
              <div className="filter-card">
                <div className="filter-title">카테고리</div>
                <div className="filter-links">
                  {categoryQuick.map((category) => (
                    <button
                      key={'code' in category ? category.code : category.label}
                      type="button"
                      className="filter-chip"
                      onClick={() =>
                        'code' in category ? handleCategoryClick(category.code) : handleExampleClick(category.query)
                      }
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="filter-card">
                <div className="filter-title">검색 확장</div>
                <p className="filter-note">현재 검색어에 아래 키워드를 더해보세요.</p>
                <div className="filter-links">
                  {REFINE_TAGS.map((tag) => (
                    <button key={tag} type="button" className="filter-chip" onClick={() => handleRefine(tag)}>
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
              <div className="filter-card">
                <div className="filter-title">혜택 안내</div>
                <ul className="filter-list">
                  <li>2만원 이상 주문 시 무료배송</li>
                  <li>밤 11시 이전 주문 시 내일 도착</li>
                  <li>7일 무료 반품</li>
                </ul>
              </div>
            </aside>

            <div className="search-main">
              <div className="results-header">
                <div>
                  <h2 className="section-title">{resultsTitle}</h2>
                  <div className="text-muted small">
                    {totalCount.toLocaleString()}개 결과 · {currentStart.toLocaleString()}-{currentEnd.toLocaleString()} 표시
                  </div>
                </div>
                <div className="results-toolbar">
                  <div className="btn-group view-toggle" role="group" aria-label="Result view">
                    <button
                      type="button"
                      className={`btn btn-outline-dark btn-sm ${viewMode === 'card' ? 'active' : ''}`}
                      onClick={() => setViewMode('card')}
                    >
                      그리드
                    </button>
                    <button
                      type="button"
                      className={`btn btn-outline-dark btn-sm ${viewMode === 'compact' ? 'active' : ''}`}
                      onClick={() => setViewMode('compact')}
                    >
                      리스트
                    </button>
                  </div>
                  <button
                    className="btn btn-outline-secondary btn-sm"
                    type="button"
                    onClick={executeSearch}
                    disabled={loading}
                  >
                    {loading ? '검색 중...' : '다시 검색'}
                  </button>
                </div>
              </div>

              <details className="advanced-panel">
                <summary>고급 검색 옵션</summary>
                <div className="advanced-content">
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
                      Vector 검색
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
                </div>
              </details>

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
                      <div className="debug-label">trace_id</div>
                      <div className="debug-value">{traceId}</div>
                    </div>
                    <div>
                      <div className="debug-label">request_id</div>
                      <div className="debug-value">{requestId}</div>
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
                  <div className="d-flex flex-column gap-2">
                    <div>
                      <div className="fw-semibold">검색 요청에 실패했습니다</div>
                      <div className="small">
                        {error.stage ? `${error.stage} | ` : ''}
                        {error.statusLine}
                        {error.code ? ` | ${error.code}` : ''}
                      </div>
                      {error.detail ? <pre className="error-body">{error.detail}</pre> : null}
                    </div>
                    <button
                      type="button"
                      className="btn btn-outline-light btn-sm align-self-start"
                      onClick={executeSearch}
                      disabled={loading}
                    >
                      다시 시도
                    </button>
                  </div>
                </div>
              ) : null}

              {loading ? (
                <div className="placeholder-card loading-state">
                  <div className="spinner-border text-primary" role="status" aria-label="Loading">
                    <span className="visually-hidden">Loading</span>
                  </div>
                  <div>도서를 찾는 중...</div>
                </div>
              ) : null}

              {!loading && !error && hasSearched && hits.length === 0 ? (
                <div className="placeholder-card empty-state">
                  <div className="empty-title">검색 결과가 없습니다</div>
                  <div className="empty-copy">다른 키워드로 다시 검색해보세요.</div>
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
                <>
                  <div className={`results-list ${viewMode}-view`} aria-label={viewLabel}>
                    {hits.map((hit, index) => {
                      const itemPosition = fromValue + index + 1
                    const source = hit.source ?? {}
                    const title = source.title_ko ?? 'Untitled'
                    const authors = Array.isArray(source.authors) ? source.authors.join(', ') : '-'
                    const publisher = source.publisher_name ?? '-'
                    const issuedYear = source.issued_year ?? '-'
                    const editions = Array.isArray(source.edition_labels)
                      ? source.edition_labels.slice(0, 3)
                      : []
                    const isbn13 = typeof source.isbn13 === 'string' ? source.isbn13 : null
                    const coverUrl = typeof source.cover_url === 'string' ? source.cover_url : null
                    const score = typeof hit.score === 'number' ? hit.score : null
                    const docId = hit.doc_id
                    const docLink = docId ? `/book/${encodeURIComponent(docId)}?from=search` : null
                    const debug = getHitDebug(hit)
                    const debugEntries = Object.entries(debug).filter(([, value]) => value !== undefined)

                    return (
                      <article
                        key={docId ?? `${title}-${itemPosition}`}
                        className={viewMode === 'card' ? 'result-tile' : 'result-tile compact'}
                      >
                        <div className="result-cover">
                          <BookCover
                            className="result-cover-image"
                            title={title}
                            coverUrl={coverUrl}
                            isbn13={isbn13}
                            docId={docId ?? null}
                            size="M"
                          />
                          <span className="result-rank">#{hit.rank ?? itemPosition}</span>
                        </div>
                        <div className="result-content">
                          <div className="result-header">
                            {docLink ? (
                              <Link
                                className="result-title"
                                to={docLink}
                                onClick={() => handleSelectHit(hit, itemPosition)}
                              >
                                {title}
                              </Link>
                            ) : (
                              <span className="result-title">{title}</span>
                            )}
                            {debugEnabled && score !== null ? (
                              <span className="score-badge">Score {score.toFixed(3)}</span>
                            ) : null}
                          </div>
                          <div className="result-meta">{authors}</div>
                          <div className="result-meta">
                            {publisher} · {issuedYear}
                          </div>
                          <div className="result-tags">
                            {editions.length > 0 ? (
                              editions.map((edition) => (
                                <span key={edition} className="tag-chip">
                                  {edition}
                                </span>
                              ))
                            ) : (
                              <span className="tag-chip muted">판형 정보 없음</span>
                            )}
                          </div>
                          {debugEnabled && debugEntries.length > 0 ? (
                            <div className="result-debug">
                              {debugEntries.map(([key, value]) => (
                                <span key={key}>
                                  {key}: {String(value)}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          <div className="result-actions">
                            {docLink ? (
                              <Link
                                to={docLink}
                                className="btn btn-outline-dark btn-sm"
                                onClick={() => handleSelectHit(hit, itemPosition)}
                              >
                                상세보기
                              </Link>
                            ) : null}
                            <button
                              type="button"
                              className="btn btn-outline-secondary btn-sm"
                              onClick={() => handleSimilarBooks(title, docId ?? undefined)}
                            >
                              비슷한 책
                            </button>
                          </div>
                        </div>
                      </article>
                    )
                    })}
                  </div>
                  {totalPages > 1 ? (
                    <nav className="mt-4" aria-label="검색 결과 페이지네이션">
                      <ul className="pagination pagination-sm mb-0">
                        <li className={`page-item ${hasPrevPage ? '' : 'disabled'}`}>
                          <button
                            type="button"
                            className="page-link"
                            onClick={() => updateParams({ page: pageValue - 1 })}
                            disabled={!hasPrevPage || loading}
                          >
                            이전
                          </button>
                        </li>
                        {pageNumbers.map((pageNum) => (
                          <li key={pageNum} className={`page-item ${pageNum === pageValue ? 'active' : ''}`}>
                            <button
                              type="button"
                              className="page-link"
                              onClick={() => updateParams({ page: pageNum })}
                              disabled={loading}
                            >
                              {pageNum}
                            </button>
                          </li>
                        ))}
                        <li className={`page-item ${hasNextPage ? '' : 'disabled'}`}>
                          <button
                            type="button"
                            className="page-link"
                            onClick={() => updateParams({ page: pageValue + 1 })}
                            disabled={!hasNextPage || loading}
                          >
                            다음
                          </button>
                        </li>
                      </ul>
                    </nav>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

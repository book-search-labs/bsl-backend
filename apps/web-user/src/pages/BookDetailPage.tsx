import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { getBookDetail } from '../api/books'
import { HttpError } from '../api/http'
import { postSearchDwell, search } from '../api/searchApi'
import type { Book, BookHit } from '../types/search'
import { addRecentView } from '../utils/recentViews'

const STORAGE_PREFIX = 'bsl:lastHit:'

type CachedHit = {
  doc_id?: string
  imp_id?: string
  query_hash?: string
  position?: number
  source?: {
    title_ko?: string
    authors?: string[]
    publisher_name?: string
    issued_year?: number
    volume?: number
    edition_labels?: string[]
    [key: string]: unknown
  } | null
  fromQuery?: {
    q?: string
    size?: number
    vector?: boolean
  }
  ts?: number
}

function readCachedHit(docId?: string) {
  if (!docId) return null
  try {
    const raw = sessionStorage.getItem(`${STORAGE_PREFIX}${docId}`)
    if (!raw) return null
    return JSON.parse(raw) as CachedHit
  } catch {
    return null
  }
}

function joinAuthors(authors: string[]) {
  return authors.length > 0 ? authors.join(', ') : '저자 정보 없음'
}

function mapCachedToBook(docId: string, cached: CachedHit): Book {
  const source = cached.source ?? {}
  return {
    docId,
    titleKo: source.title_ko ?? null,
    authors: Array.isArray(source.authors) ? source.authors : [],
    publisherName: source.publisher_name ?? null,
    issuedYear: source.issued_year ?? null,
    volume: source.volume ?? null,
    editionLabels: Array.isArray(source.edition_labels) ? source.edition_labels : [],
  }
}

function parseBooleanParam(value: string | null) {
  if (value == null) return undefined
  const v = value.trim().toLowerCase()
  if (v === 'true' || v === '1' || v === 'yes' || v === 'y') return true
  if (v === 'false' || v === '0' || v === 'no' || v === 'n') return false
  return undefined
}

function parseNumberParam(value: string | null) {
  if (value == null) return undefined
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : undefined
}

function writeCachedHit(
  docId: string,
  source?: CachedHit['source'],
  fromQuery?: CachedHit['fromQuery'],
  eventContext?: Pick<CachedHit, 'imp_id' | 'query_hash' | 'position'>,
) {
  const payload: CachedHit = {
    doc_id: docId,
    source: source ?? null,
    fromQuery: fromQuery ?? undefined,
    imp_id: eventContext?.imp_id,
    query_hash: eventContext?.query_hash,
    position: eventContext?.position,
    ts: Date.now(),
  }

  try {
    sessionStorage.setItem(`${STORAGE_PREFIX}${docId}`, JSON.stringify(payload))
  } catch {
    // Ignore storage failures
  }
}

export default function BookDetailPage() {
  const { docId } = useParams()
  const [pageParams] = useSearchParams()

  const fromParam = pageParams.get('from')

  // (optional) if you append these when navigating from search results:
  // /book/:docId?from=search&q=...&size=...&vector=true
  const qParam = pageParams.get('q') ?? undefined
  const sizeParam = parseNumberParam(pageParams.get('size'))
  const vectorParam = parseBooleanParam(pageParams.get('vector'))

  const fromQueryFromUrl = useMemo<CachedHit['fromQuery'] | undefined>(() => {
    if (fromParam !== 'search') return undefined
    if (!qParam && sizeParam === undefined && vectorParam === undefined) return undefined
    return {
      q: qParam,
      size: sizeParam,
      vector: vectorParam,
    }
  }, [fromParam, qParam, sizeParam, vectorParam])

  const [cachedHit, setCachedHit] = useState<CachedHit | null>(null)
  const dwellContextRef = useRef<CachedHit | null>(null)
  const [book, setBook] = useState<Book | null>(null)

  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [retryToken, setRetryToken] = useState(0)

  const [similarHits, setSimilarHits] = useState<BookHit[]>([])
  const [similarLoading, setSimilarLoading] = useState(false)

  useEffect(() => {
    let isActive = true

    if (!docId) {
      setError('Missing document id.')
      setNotFound(true)
      return () => {
        isActive = false
      }
    }

    // 1) Read cache first for instant render
    const cached = readCachedHit(docId)
    setCachedHit(cached)
    dwellContextRef.current = cached

    const hasCached = Boolean(cached && cached.source)

    if (hasCached) {
      const cachedBook = mapCachedToBook(docId, cached as CachedHit)
      setBook(cachedBook)
      setLoading(false)
      setError(null)
      setNotFound(false)

      addRecentView({
        docId: cachedBook.docId,
        titleKo: cachedBook.titleKo,
        authors: cachedBook.authors,
        viewedAt: Date.now(),
      })
    } else {
      setBook(null)
      setLoading(true)
      setError(null)
      setNotFound(false)
    }

    // 2) stale-while-revalidate: even if cached exists, fetch in background to refresh
    //    (dont show blocking spinner if we already have cached data)
    if (hasCached) {
      setRefreshing(true)
    }

    getBookDetail(docId)
      .then((result) => {
        if (!isActive) return

        if (!result || !result.source) {
          // If no cached book, this is truly not found / empty
          if (!hasCached) {
            setBook(null)
            setNotFound(true)
          }
          return
        }

        const resolvedDocId = result.doc_id ?? docId

        const nextBook: Book = {
          docId: resolvedDocId,
          titleKo: result.source.title_ko ?? null,
          authors: Array.isArray(result.source.authors) ? result.source.authors : [],
          publisherName: result.source.publisher_name ?? null,
          issuedYear: result.source.issued_year ?? null,
          volume: result.source.volume ?? null,
          editionLabels: Array.isArray(result.source.edition_labels) ? result.source.edition_labels : [],
        }

        setBook(nextBook)
        setError(null)
        setNotFound(false)

        // If user came from search, persist the return to results context.
        // Prefer URL params (if present), otherwise keep existing cached fromQuery.
        const mergedFromQuery = fromQueryFromUrl ?? cached?.fromQuery

        writeCachedHit(resolvedDocId, result.source ?? null, mergedFromQuery, {
          imp_id: cached?.imp_id,
          query_hash: cached?.query_hash,
          position: cached?.position,
        })
        setCachedHit({
          doc_id: resolvedDocId,
          source: result.source ?? null,
          fromQuery: mergedFromQuery,
          imp_id: cached?.imp_id,
          query_hash: cached?.query_hash,
          position: cached?.position,
          ts: Date.now(),
        })
        dwellContextRef.current = {
          doc_id: resolvedDocId,
          source: result.source ?? null,
          fromQuery: mergedFromQuery,
          imp_id: cached?.imp_id,
          query_hash: cached?.query_hash,
          position: cached?.position,
          ts: Date.now(),
        }

        addRecentView({
          docId: nextBook.docId,
          titleKo: nextBook.titleKo,
          authors: nextBook.authors,
          viewedAt: Date.now(),
        })
      })
      .catch((err) => {
        if (!isActive) return

        if (err instanceof HttpError && err.status === 404) {
          // If no cached content, show not found.
          // If cached exists, keep cached view (dont nuke the page).
          if (!hasCached) {
            setNotFound(true)
          }
          return
        }

        const message =
          err instanceof HttpError
            ? err.message || err.statusText
            : err instanceof Error
              ? err.message
              : String(err)

        // If cached exists, show non-blocking error (keep page content)
        // If not cached, show blocking error state
        setError(message)
      })
      .finally(() => {
        if (!isActive) return
        setLoading(false)
        setRefreshing(false)
      })

    return () => {
      isActive = false
    }
  }, [docId, retryToken, fromQueryFromUrl])

  useEffect(() => {
    if (!docId) return
    const startedAt = Date.now()
    return () => {
      const context = dwellContextRef.current
      if (!context?.imp_id || !context?.query_hash || !context?.position) {
        return
      }
      const dwellMs = Math.max(0, Date.now() - startedAt)
      postSearchDwell({
        imp_id: context.imp_id,
        doc_id: docId,
        position: context.position,
        query_hash: context.query_hash,
        dwell_ms: dwellMs,
      }).catch(() => {
        // Ignore event failures
      })
    }
  }, [docId])

  const backLink = useMemo(() => {
    if (fromParam === 'search') {
      const q = cachedHit?.fromQuery?.q
      if (q) {
        const params = new URLSearchParams()
        params.set('q', q)

        if (cachedHit?.fromQuery?.size) {
          params.set('size', String(cachedHit.fromQuery.size))
        }
        if (cachedHit?.fromQuery?.vector !== undefined) {
          params.set('vector', cachedHit.fromQuery.vector ? 'true' : 'false')
        }
        return `/search?${params.toString()}`
      }
    }
    return '/search'
  }, [cachedHit, fromParam])

  const similarQuery = book?.titleKo ?? cachedHit?.source?.title_ko ?? ''
  const similarLink = similarQuery ? `/search?q=${encodeURIComponent(similarQuery)}` : '/search'

  useEffect(() => {
    if (!similarQuery) {
      setSimilarHits([])
      return
    }

    let active = true
    setSimilarLoading(true)

    search(similarQuery, { size: 6, from: 0, vector: true })
      .then((response) => {
        if (!active) return
        const filtered = (response.hits ?? []).filter((hit) => hit.doc_id !== docId)
        setSimilarHits(filtered.slice(0, 6))
      })
      .catch(() => {
        if (!active) return
        setSimilarHits([])
      })
      .finally(() => {
        if (!active) return
        setSimilarLoading(false)
      })

    return () => {
      active = false
    }
  }, [docId, similarQuery])

  const title = book?.titleKo ?? cachedHit?.source?.title_ko ?? 'Untitled'
  const authors = book?.authors ?? (cachedHit?.source?.authors ?? [])
  const publisher = book?.publisherName ?? cachedHit?.source?.publisher_name ?? '-'
  const issuedYear = book?.issuedYear ?? cachedHit?.source?.issued_year ?? '-'
  const volume = book?.volume ?? cachedHit?.source?.volume ?? '-'
  const editionLabels = book?.editionLabels ?? (cachedHit?.source?.edition_labels ?? [])

  const showNotFound = !loading && !error && notFound && !book && !(cachedHit && cachedHit.source)
  const showDetail = !loading && !showNotFound && (book || (cachedHit && cachedHit.source))

  return (
    <section className="page-section">
      <div className="container py-5 detail-page">
        <div className="detail-header">
          <div className="detail-breadcrumb">
            <Link to="/">홈</Link>
            <span>/</span>
            <Link to={backLink}>검색 결과</Link>
            <span>/</span>
            <span>{title}</span>
          </div>
          <div className="detail-header-actions">
            <Link className="btn btn-outline-secondary btn-sm" to={backLink}>
              검색 결과로
            </Link>
            <Link className="btn btn-primary btn-sm" to={similarLink}>
              비슷한 책 보기
            </Link>
          </div>
        </div>

        {refreshing ? <div className="small text-muted">새로고침 중...</div> : null}

        {error ? (
          <div className="alert alert-danger" role="alert">
            <div className="fw-semibold">도서 정보를 불러오지 못했습니다</div>
            <div className="small">{error}</div>
            <button
              type="button"
              className="btn btn-outline-light btn-sm mt-2"
              onClick={() => setRetryToken((value) => value + 1)}
              disabled={loading}
            >
              다시 시도
            </button>
          </div>
        ) : null}

        {loading && !book && !(cachedHit && cachedHit.source) ? (
          <div className="placeholder-card loading-state">
            <div className="spinner-border text-primary" role="status" aria-label="Loading">
              <span className="visually-hidden">Loading</span>
            </div>
            <div>도서 정보를 불러오는 중...</div>
          </div>
        ) : null}

        {showNotFound ? (
          <div className="placeholder-card empty-state">
            <div className="empty-title">도서를 찾을 수 없습니다</div>
            <div className="empty-copy">다른 키워드로 검색해보세요.</div>
            <Link className="btn btn-outline-dark btn-sm" to={backLink}>
              검색으로 이동
            </Link>
          </div>
        ) : null}

        {showDetail ? (
          <div className="detail-grid">
            <div className="detail-cover">
              <div className="detail-cover-inner">
                <span className="detail-cover-label">BSL Pick</span>
                <span className="detail-cover-title">{title}</span>
                <span className="detail-cover-meta">{joinAuthors(authors)}</span>
              </div>
              <div className="detail-actions">
                <Link className="btn btn-primary" to={similarLink}>
                  비슷한 책 찾기
                </Link>
                <Link className="btn btn-outline-secondary" to="/chat">
                  책봇 추천 받기
                </Link>
              </div>
            </div>
            <div className="detail-info">
              <h1 className="detail-title">{title}</h1>
              <div className="detail-subtitle">{joinAuthors(authors)}</div>
              <div className="detail-meta">
                {publisher} · {issuedYear} · Volume {volume}
              </div>
              <div className="detail-tags">
                {editionLabels.length > 0 ? (
                  editionLabels.map((label) => (
                    <span key={label} className="tag-chip">
                      {label}
                    </span>
                  ))
                ) : (
                  <span className="tag-chip muted">판형 정보 없음</span>
                )}
              </div>
              <div className="detail-info-grid">
                <div>
                  <span className="detail-info-label">발행 연도</span>
                  <span className="detail-info-value">{issuedYear}</span>
                </div>
                <div>
                  <span className="detail-info-label">권수</span>
                  <span className="detail-info-value">{volume}</span>
                </div>
                <div>
                  <span className="detail-info-label">Doc ID</span>
                  <span className="detail-info-value">{docId ?? '-'}</span>
                </div>
              </div>
            </div>
            <aside className="detail-aside">
              <div className="detail-aside-card">
                <div className="detail-aside-title">배송/혜택</div>
                <ul>
                  <li>2만원 이상 주문 시 무료배송</li>
                  <li>밤 11시 전 주문 시 내일 도착</li>
                  <li>7일 무료 반품</li>
                </ul>
              </div>
              <div className="detail-aside-card">
                <div className="detail-aside-title">추천 기능</div>
                <p>책봇에게 취향을 알려주면 맞춤 도서를 추천해드립니다.</p>
                <Link to="/chat" className="btn btn-outline-dark btn-sm">
                  책봇 바로가기
                </Link>
              </div>
            </aside>
          </div>
        ) : null}

        <div className="detail-section">
          <div className="section-header">
            <div>
              <h2 className="section-title">비슷한 책 추천</h2>
              <p className="section-note">현재 도서와 유사한 주제를 가진 책을 모았습니다.</p>
            </div>
            <Link to={similarLink} className="section-link">
              더 보기
            </Link>
          </div>
          {similarLoading ? (
            <div className="shelf-grid">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={`similar-skeleton-${index}`} className="book-tile skeleton" />
              ))}
            </div>
          ) : similarHits.length > 0 ? (
            <div className="shelf-grid">
              {similarHits.map((hit, index) => {
                const source = hit.source ?? {}
                const similarTitle = source.title_ko ?? '제목 없음'
                const similarAuthors = Array.isArray(source.authors) ? source.authors.join(', ') : '-'
                const docLink = hit.doc_id
                  ? `/book/${encodeURIComponent(hit.doc_id)}?from=similar`
                  : `/search?q=${encodeURIComponent(similarTitle)}`

                return (
                  <article key={hit.doc_id ?? `similar-${index}`} className="book-tile">
                    <div className="book-tile-cover">
                      <span className="book-tile-rank">#{index + 1}</span>
                      <span className="book-tile-cover-title">{similarTitle}</span>
                    </div>
                    <div className="book-tile-body">
                      <h3 className="book-tile-title">{similarTitle}</h3>
                      <p className="book-tile-meta">{similarAuthors}</p>
                      <div className="book-tile-actions">
                        <Link className="btn btn-outline-dark btn-sm" to={docLink}>
                          상세보기
                        </Link>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <div className="placeholder-card empty-state">
              <div className="empty-title">추천 도서가 없습니다</div>
              <div className="empty-copy">다른 키워드로 검색해보세요.</div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

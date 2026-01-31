import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { HttpError } from '../api/http'
import { getBookDetail } from '../api/books'
import { postSearchDwell } from '../api/searchApi'
import type { Book } from '../types/search'
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
  return authors.length > 0 ? authors.join(', ') : '-'
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
    //    (don’t show blocking spinner if we already have cached data)
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

      // If user came from search, persist the “return to results” context.
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
        // If cached exists, keep cached view (don’t nuke the page).
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
      <div className="container py-5">
        <div className="d-flex flex-column gap-4">
          <div className="d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-3">
            <div>
              <h1 className="page-title">Book Detail</h1>
              <p className="page-lead">Book metadata pulled from the Search Service.</p>
              {refreshing ? (
                <div className="small text-muted">Refreshing…</div>
              ) : null}
            </div>
            <div className="d-flex flex-wrap gap-2">
              <Link className="btn btn-outline-secondary btn-sm" to={backLink}>
                Back to results
              </Link>
              <Link className="btn btn-primary btn-sm" to={similarLink}>
                Search similar
              </Link>
            </div>
          </div>

          {error ? (
            <div className="alert alert-danger" role="alert">
              <div className="fw-semibold">Unable to load book</div>
              <div className="small">{error}</div>
              <button
                type="button"
                className="btn btn-outline-light btn-sm mt-2"
                onClick={() => setRetryToken((value) => value + 1)}
                disabled={loading}
              >
                Retry
              </button>
            </div>
          ) : null}

          {loading && !book && !(cachedHit && cachedHit.source) ? (
            <div className="placeholder-card loading-state">
              <div className="spinner-border text-primary" role="status" aria-label="Loading">
                <span className="visually-hidden">Loading</span>
              </div>
              <div>Loading book details...</div>
            </div>
          ) : null}

          {showNotFound ? (
            <div className="placeholder-card empty-state">
              <div className="empty-title">Book not found</div>
              <div className="empty-copy">
                We could not find this book yet. Try searching again or check the doc id.
              </div>
              <Link className="btn btn-outline-dark btn-sm" to={backLink}>
                Back to search
              </Link>
            </div>
          ) : null}

          {showDetail ? (
            <div className="card shadow-sm detail-card">
              <div className="card-body">
                <div className="detail-title">{title}</div>
                <div className="detail-meta">{joinAuthors(authors)}</div>
                <div className="detail-meta">
                  {publisher} | Year {issuedYear} | Volume {volume}
                </div>

                <div className="mt-3 d-flex flex-wrap gap-2">
                  {editionLabels.length > 0 ? (
                    editionLabels.map((label) => (
                      <span key={label} className="badge text-bg-light border">
                        {label}
                      </span>
                    ))
                  ) : (
                    <span className="text-muted small">No edition labels</span>
                  )}
                </div>

                <div className="mt-4">
                  <div className="text-muted small">Doc ID</div>
                  <div className="fw-semibold">{docId ?? '-'}</div>
                </div>

                {/* (optional) if you want to debug the return context */}
                {/* {cachedHit?.fromQuery ? (
                  <pre className="mt-3 small bg-light border rounded p-2">
                    {JSON.stringify(cachedHit.fromQuery, null, 2)}
                  </pre>
                ) : null} */}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  )
}

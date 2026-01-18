import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { HttpError } from '../api/http'
import { searchByDocId } from '../api/searchApi'
import type { Book } from '../types/search'
import { addRecentView } from '../utils/recentViews'

const STORAGE_PREFIX = 'bsl:lastHit:'

type CachedHit = {
  doc_id?: string
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

export default function BookDetailPage() {
  const { docId } = useParams()
  const [pageParams] = useSearchParams()
  const fromParam = pageParams.get('from')

  const [cachedHit, setCachedHit] = useState<CachedHit | null>(null)
  const [book, setBook] = useState<Book | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    setCachedHit(readCachedHit(docId))
  }, [docId])

  useEffect(() => {
    let isActive = true

    if (!docId) {
      setError('Missing document id.')
      setNotFound(true)
      return () => {
        isActive = false
      }
    }

    setLoading(true)
    setError(null)
    setNotFound(false)

    searchByDocId(docId)
      .then((result) => {
        if (!isActive) return
        if (!result) {
          setBook(null)
          setNotFound(true)
          return
        }
        setBook(result)
        addRecentView({
          docId: result.docId,
          titleKo: result.titleKo,
          authors: result.authors,
          viewedAt: Date.now(),
        })
      })
      .catch((err) => {
        if (!isActive) return
        const message =
          err instanceof HttpError
            ? err.message || err.statusText
            : err instanceof Error
              ? err.message
              : String(err)
        setError(message)
      })
      .finally(() => {
        if (isActive) setLoading(false)
      })

    return () => {
      isActive = false
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

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="d-flex flex-column gap-4">
          <div className="d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-3">
            <div>
              <h1 className="page-title">Book Detail</h1>
              <p className="page-lead">Book metadata pulled from the Search Service.</p>
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
            </div>
          ) : null}

          {loading ? (
            <div className="placeholder-card loading-state">
              <div className="spinner-border text-primary" role="status" aria-label="Loading">
                <span className="visually-hidden">Loading</span>
              </div>
              <div>Loading book details...</div>
            </div>
          ) : null}

          {!loading && !error && notFound ? (
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

          {!loading && !error && !notFound ? (
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
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  )
}

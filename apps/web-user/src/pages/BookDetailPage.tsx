import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

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
  debug?: Record<string, unknown> | null
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

export default function BookDetailPage() {
  const { docId } = useParams()
  const [cachedHit, setCachedHit] = useState<CachedHit | null>(null)

  useEffect(() => {
    setCachedHit(readCachedHit(docId))
  }, [docId])

  const source = cachedHit?.source ?? {}
  const authors = Array.isArray(source.authors) ? source.authors.join(', ') : '-'
  const editions = Array.isArray(source.edition_labels)
    ? source.edition_labels.join(', ')
    : '-'
  const issuedYear = source.issued_year ?? '-'
  const volume = source.volume ?? '-'
  const cachedAt = cachedHit?.ts ? new Date(cachedHit.ts).toISOString() : '-'

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="row">
          <div className="col-lg-8">
            <h1 className="page-title">Book Detail</h1>
            <p className="page-lead">Saved preview from your last search click.</p>
            <div className="placeholder-card detail-card">
              <div className="d-flex flex-column gap-3">
                <div>
                  <h2 className="section-title">Document ID</h2>
                  <p className="section-note">Cached payload is stored in sessionStorage.</p>
                </div>
                <div className="query-pill">{docId || '(missing doc id)'}</div>

                {cachedHit ? (
                  <div className="detail-body">
                    <div className="detail-title">{source.title_ko ?? 'Untitled'}</div>
                    <div className="detail-meta">{authors}</div>
                    <div className="detail-meta">
                      {source.publisher_name ?? '-'} | Year {issuedYear} | Volume {volume}
                    </div>
                    <div className="detail-meta">Editions: {editions}</div>
                    <div className="detail-meta">Cached at: {cachedAt}</div>
                    <div className="detail-meta">
                      From query: {cachedHit.fromQuery?.q ?? '-'} (size{' '}
                      {cachedHit.fromQuery?.size ?? '-'})
                    </div>
                    <details className="debug-panel nested">
                      <summary>Cached payload</summary>
                      <pre>{JSON.stringify(cachedHit, null, 2)}</pre>
                    </details>
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-title">No cached payload</div>
                    <div className="empty-copy">Go back to search and select a result.</div>
                    <Link className="btn btn-outline-dark btn-sm" to="/search">
                      Back to search
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

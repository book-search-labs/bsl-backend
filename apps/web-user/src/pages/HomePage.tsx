import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { clearRecentViews, getRecentViews } from '../utils/recentViews'
import type { RecentView } from '../utils/recentViews'

const categories = [
  'Fantasy & Myth',
  'Korean Fiction',
  'Non-fiction Classics',
  'YA Adventures',
  'Mystery & Crime',
  'Sci-Fi Futures',
]

export default function HomePage() {
  const sampleQuery = '해리포터 1권'
  const sampleLink = `/search?q=${encodeURIComponent(sampleQuery)}`
  const [recentViews, setRecentViews] = useState<RecentView[]>([])

  useEffect(() => {
    setRecentViews(getRecentViews().slice(0, 5))
  }, [])

  const handleClear = () => {
    clearRecentViews()
    setRecentViews([])
  }

  return (
    <section className="home-page">
      <div className="container py-5">
        <div className="row g-4 align-items-stretch">
          <div className="col-lg-7">
            <div className="hero-card h-100">
              <p className="hero-eyebrow">Book-first discovery</p>
              <h1 className="hero-title">Find the edition you remember.</h1>
              <p className="hero-lead">
                BSL Books helps you trace the right printing, series, and translation with a
                reader-friendly experience built for real shelves.
              </p>
              <p className="try-search">
                Try searching: <Link to={sampleLink}>{sampleQuery}</Link>
              </p>
              <div className="chip-list">
                {categories.map((category) => (
                  <button key={category} type="button" className="btn btn-outline-secondary chip">
                    {category}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="col-lg-5">
            <div className="feature-panel h-100">
              <h2 className="feature-title">What the MVP includes</h2>
              <ul className="feature-list list-unstyled">
                <li>
                  <span className="feature-label">Global search shell</span>
                  <span>Always-on search with query carry-through.</span>
                </li>
                <li>
                  <span className="feature-label">Book-friendly layout</span>
                  <span>Soft typography, shelf-like spacing, and crisp navigation.</span>
                </li>
                <li>
                  <span className="feature-label">Next: real results</span>
                  <span>Search results and book detail data land in the next tickets.</span>
                </li>
              </ul>
              <div className="feature-actions">
                <Link className="btn btn-primary" to="/search">
                  Explore search
                </Link>
                <Link className="btn btn-outline-dark" to="/about">
                  See env setup
                </Link>
              </div>
            </div>
          </div>
        </div>
        <div className="row mt-5">
          <div className="col-lg-8">
            <div className="card shadow-sm">
              <div className="card-body">
                <div className="d-flex flex-column flex-sm-row align-items-sm-center justify-content-between gap-2">
                  <h2 className="feature-title mb-0">Recently viewed</h2>
                  <button
                    type="button"
                    className="btn btn-outline-secondary btn-sm"
                    onClick={handleClear}
                    disabled={recentViews.length === 0}
                  >
                    Clear
                  </button>
                </div>
                {recentViews.length > 0 ? (
                  <ul className="list-group list-group-flush mt-3">
                    {recentViews.map((item) => (
                      <li key={item.docId} className="list-group-item px-0">
                        <Link to={`/book/${encodeURIComponent(item.docId)}?from=recent`}>
                          {item.titleKo ?? 'Untitled'}
                        </Link>
                        <div className="text-muted small">
                          {item.authors.length > 0 ? item.authors.join(', ') : '-'}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted mt-3 mb-0">No recently viewed books yet.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

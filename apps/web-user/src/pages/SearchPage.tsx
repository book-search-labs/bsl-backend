import { useSearchParams } from 'react-router-dom'

export default function SearchPage() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') ?? ''

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="row">
          <div className="col-lg-8">
            <h1 className="page-title">Search</h1>
            <p className="page-lead">
              {query
                ? 'Showing placeholder results for your query.'
                : 'Use the search bar above to explore titles, authors, and series.'}
            </p>
            <div className="placeholder-card">
              <div className="d-flex flex-column gap-3">
                <div>
                  <h2 className="section-title">Query snapshot</h2>
                  <p className="section-note">Search results will render here in the next sprint.</p>
                </div>
                <div className="query-pill">{query || '(no query yet)'}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

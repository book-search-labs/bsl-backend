export default function AboutPage() {
  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL
  const queryBaseUrl = import.meta.env.VITE_QUERY_BASE_URL
  const bffBaseUrl = import.meta.env.VITE_BFF_BASE_URL
  const apiMode = import.meta.env.VITE_API_MODE
  const envPreview = `VITE_BFF_BASE_URL=${bffBaseUrl || '(unset)'}\nVITE_API_MODE=${apiMode || '(unset)'}\nVITE_SEARCH_BASE_URL=${searchBaseUrl || '(unset)'}\nVITE_QUERY_BASE_URL=${queryBaseUrl || '(unset)'}`

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="row">
          <div className="col-lg-7">
            <h1 className="page-title">About</h1>
            <p className="page-lead">
              BSL Books is an MVP UI for book-centric search. API integrations and real data
              flow in the next phase.
            </p>
            <div className="placeholder-card">
              <h2 className="section-title">Environment</h2>
              <p className="section-note">
                These values are pulled from the Vite environment for local sanity checks.
              </p>
              <pre className="env-preview">{envPreview}</pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

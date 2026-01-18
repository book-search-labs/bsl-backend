import { useParams } from 'react-router-dom'

export default function BookDetailPage() {
  const { docId } = useParams()

  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="row">
          <div className="col-lg-8">
            <h1 className="page-title">Book Detail</h1>
            <p className="page-lead">This page will show edition metadata and availability.</p>
            <div className="placeholder-card">
              <div className="d-flex flex-column gap-3">
                <div>
                  <h2 className="section-title">Document ID</h2>
                  <p className="section-note">Fetched detail data will render here next.</p>
                </div>
                <div className="query-pill">{docId || '(missing doc id)'}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

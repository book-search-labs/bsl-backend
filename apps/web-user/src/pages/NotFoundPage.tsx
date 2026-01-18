import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <section className="page-section">
      <div className="container py-5">
        <div className="row">
          <div className="col-lg-7">
            <h1 className="page-title">Page not found</h1>
            <p className="page-lead">
              The shelf you were looking for does not exist yet. Head back to the main stacks.
            </p>
            <Link to="/" className="btn btn-primary">
              Back to home
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

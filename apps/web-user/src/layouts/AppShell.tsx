import { type FormEvent, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState('')

  useEffect(() => {
    if (location.pathname.startsWith('/search')) {
      const nextQuery = searchParams.get('q') ?? ''
      setQuery(nextQuery)
    }
  }, [location.pathname, location.search, searchParams])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = query.trim()

    if (trimmed.length > 0) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`)
      return
    }

    navigate('/search')
  }

  const navLinkClassName = ({ isActive }: { isActive: boolean }) =>
    `nav-link ${isActive ? 'active' : ''}`

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="container py-3 py-lg-4">
          <div className="d-flex flex-column gap-3 gap-lg-4">
            <div className="d-flex flex-column flex-lg-row align-items-lg-center justify-content-between gap-3">
              <Link to="/" className="brand d-inline-flex align-items-center gap-3">
                <span className="brand-mark">BSL</span>
                <span className="brand-text">
                  <span className="brand-title">BSL Books</span>
                  <span className="brand-subtitle">Book Search Labs</span>
                </span>
              </Link>
              <nav className="app-nav nav nav-pills gap-1">
                <NavLink to="/" end className={navLinkClassName}>
                  Home
                </NavLink>
                <NavLink to="/search" className={navLinkClassName}>
                  Search
                </NavLink>
                <NavLink to="/about" className={navLinkClassName}>
                  About
                </NavLink>
              </nav>
            </div>
            <form className="search-form d-flex flex-column flex-lg-row gap-2" onSubmit={handleSubmit}>
              <label className="visually-hidden" htmlFor="global-search">
                Search books
              </label>
              <input
                id="global-search"
                className="form-control form-control-lg"
                type="search"
                placeholder="Search titles, authors, ISBN, or series"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <button className="btn btn-primary btn-lg" type="submit">
                Search
              </button>
            </form>
          </div>
        </div>
      </header>

      <main className="app-main">
        <Outlet />
      </main>

      <footer className="app-footer mt-auto">
        <div className="container py-4">
          <small>BSL Book Search Labs — MVP</small>
        </div>
      </footer>
    </div>
  )
}

import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { fetchAutocomplete, type AutocompleteSuggestion } from '../api/autocomplete'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useOutsideClick } from '../hooks/useOutsideClick'

const AUTOCOMPLETE_SIZE = 8
const AUTOCOMPLETE_DEBOUNCE_MS = 250
const MIN_QUERY_LENGTH = 1
const AUTOCOMPLETE_LISTBOX_ID = 'global-search-suggestions'

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [hasFetched, setHasFetched] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const shouldSuggestRef = useRef(false)
  const debouncedQuery = useDebouncedValue(query, AUTOCOMPLETE_DEBOUNCE_MS)

  useEffect(() => {
    if (location.pathname.startsWith('/search')) {
      const nextQuery = searchParams.get('q') ?? ''
      shouldSuggestRef.current = false
      setQuery(nextQuery)
    }
  }, [location.pathname, location.search, searchParams])

  const closeSuggestions = useCallback(() => {
    setIsOpen(false)
    setActiveIndex(-1)
  }, [])

  const suppressSuggestions = useCallback(() => {
    shouldSuggestRef.current = false
    closeSuggestions()
  }, [closeSuggestions])

  useOutsideClick(formRef, () => {
    suppressSuggestions()
  })

  useEffect(() => {
    suppressSuggestions()
    setSuggestions([])
    setHasFetched(false)
    setErrorMessage(null)
  }, [location.pathname, location.search, suppressSuggestions])

  useEffect(() => {
    const trimmed = debouncedQuery.trim()

    if (!shouldSuggestRef.current || trimmed.length < MIN_QUERY_LENGTH) {
      if (trimmed.length < MIN_QUERY_LENGTH) {
        shouldSuggestRef.current = false
      }
      setIsLoading(false)
      setHasFetched(false)
      setErrorMessage(null)
      setSuggestions([])
      closeSuggestions()
      return
    }

    let isActive = true
    const controller = new AbortController()

    setIsLoading(true)
    setIsOpen(true)
    setHasFetched(false)
    setErrorMessage(null)
    setSuggestions([])
    setActiveIndex(-1)

    fetchAutocomplete(trimmed, AUTOCOMPLETE_SIZE, controller.signal)
      .then((response) => {
        if (!isActive || !shouldSuggestRef.current) return
        const items = Array.isArray(response.suggestions)
          ? response.suggestions.filter((item) => item.text && item.text.trim().length > 0)
          : []
        setSuggestions(items)
        setHasFetched(true)
        setIsOpen(true)
      })
      .catch((error) => {
        if (!isActive || (error instanceof DOMException && error.name === 'AbortError')) {
          return
        }
        setSuggestions([])
        setHasFetched(true)
        setErrorMessage('Autocomplete is unavailable right now.')
        setIsOpen(true)
      })
      .finally(() => {
        if (isActive) {
          setIsLoading(false)
        }
      })

    return () => {
      isActive = false
      controller.abort()
    }
  }, [debouncedQuery, closeSuggestions])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = query.trim()

    suppressSuggestions()

    if (trimmed.length > 0) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`)
      return
    }

    navigate('/search')
  }

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    shouldSuggestRef.current = true
    setQuery(event.target.value)
  }

  const handleSelectSuggestion = useCallback(
    (suggestion: AutocompleteSuggestion) => {
      const text = suggestion.text.trim()
      if (!text) return
      setQuery(text)
      suppressSuggestions()
      navigate(`/search?q=${encodeURIComponent(text)}`)
    },
    [navigate, suppressSuggestions],
  )

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      if (isOpen) {
        event.preventDefault()
        suppressSuggestions()
      }
      return
    }

    if (!isOpen && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      if (suggestions.length > 0) {
        event.preventDefault()
        setIsOpen(true)
        setActiveIndex(event.key === 'ArrowDown' ? 0 : suggestions.length - 1)
      }
      return
    }

    if (event.key === 'ArrowDown') {
      if (suggestions.length > 0) {
        event.preventDefault()
        setActiveIndex((prev) => (prev + 1) % suggestions.length)
      }
      return
    }

    if (event.key === 'ArrowUp') {
      if (suggestions.length > 0) {
        event.preventDefault()
        setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1))
      }
      return
    }

    if (event.key === 'Enter' && isOpen && activeIndex >= 0) {
      event.preventDefault()
      const suggestion = suggestions[activeIndex]
      if (suggestion) {
        handleSelectSuggestion(suggestion)
      }
    }
  }

  const showEmpty = hasFetched && !isLoading && suggestions.length === 0 && !errorMessage
  const showDropdown = isOpen && (isLoading || suggestions.length > 0 || showEmpty || Boolean(errorMessage))
  const activeDescendant =
    isOpen && activeIndex >= 0 ? `global-search-option-${activeIndex}` : undefined

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
            <form
              ref={formRef}
              className="search-form d-flex flex-column flex-lg-row gap-2"
              onSubmit={handleSubmit}
            >
              <label className="visually-hidden" htmlFor="global-search">
                Search books
              </label>
              <div className="typeahead-wrapper">
                <input
                  id="global-search"
                  className="form-control form-control-lg"
                  type="search"
                  placeholder="Search titles, authors, ISBN, or series"
                  value={query}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  onFocus={() => {
                    if (suggestions.length > 0 || showEmpty || errorMessage) {
                      setIsOpen(true)
                    }
                  }}
                  aria-autocomplete="list"
                  aria-controls={AUTOCOMPLETE_LISTBOX_ID}
                  aria-expanded={showDropdown}
                  aria-activedescendant={activeDescendant}
                />
                {showDropdown ? (
                  <div
                    id={AUTOCOMPLETE_LISTBOX_ID}
                    className="search-suggestions list-group"
                    role="listbox"
                  >
                    {isLoading ? (
                      <div className="list-group-item d-flex align-items-center gap-2">
                        <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true" />
                        <span>Loading suggestions...</span>
                      </div>
                    ) : null}
                    {!isLoading && errorMessage ? (
                      <div className="list-group-item text-muted small">{errorMessage}</div>
                    ) : null}
                    {!isLoading && !errorMessage
                      ? suggestions.map((suggestion, index) => {
                          const isActive = index === activeIndex
                          const itemId = `global-search-option-${index}`

                          return (
                            <button
                              key={`${suggestion.text}-${index}`}
                              id={itemId}
                              type="button"
                              role="option"
                              aria-selected={isActive}
                              className={`list-group-item list-group-item-action search-suggestion${
                                isActive ? ' active' : ''
                              }`}
                              onClick={() => handleSelectSuggestion(suggestion)}
                            >
                              {suggestion.text}
                            </button>
                          )
                        })
                      : null}
                    {showEmpty ? (
                      <div className="list-group-item text-muted small">No suggestions yet.</div>
                    ) : null}
                  </div>
                ) : null}
              </div>
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

import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { fetchAutocomplete, postAutocompleteSelect, type AutocompleteSuggestion } from '../api/autocomplete'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useOutsideClick } from '../hooks/useOutsideClick'

const AUTOCOMPLETE_SIZE = 8
const AUTOCOMPLETE_DEBOUNCE_MS = 250
const MIN_QUERY_LENGTH = 1
const AUTOCOMPLETE_LISTBOX_ID = 'global-search-suggestions'
const RECENT_STORAGE_KEY = 'bsl.recentSearches'
const MAX_RECENT = 6
const DEFAULT_RECOMMENDED = [
  '해리포터',
  '클린 코드',
  '도메인 주도 설계',
  '엘라스틱서치',
  '판타지 소설',
  '소프트웨어 아키텍처',
]

type SelectableItem = {
  kind: 'suggestion' | 'recent' | 'recommended'
  text: string
  suggestion?: AutocompleteSuggestion
  position: number
}

function loadRecentQueries(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item) => typeof item === 'string' && item.trim().length > 0)
  } catch {
    return []
  }
}

function saveRecentQueries(items: string[]) {
  try {
    localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(items))
  } catch {
    // ignore storage failures
  }
}

function resolveRecommendedQueries() {
  const raw = import.meta.env.VITE_AUTOCOMPLETE_RECOMMENDED ?? ''
  const parsed = raw
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
  return parsed.length > 0 ? parsed : DEFAULT_RECOMMENDED
}

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([])
  const [recentQueries, setRecentQueries] = useState<string[]>(() => loadRecentQueries())
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [hasFetched, setHasFetched] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const shouldSuggestRef = useRef(false)
  const debouncedQuery = useDebouncedValue(query, AUTOCOMPLETE_DEBOUNCE_MS)
  const recommendedQueries = useMemo(() => resolveRecommendedQueries(), [])

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
    const hasQuery = trimmed.length >= MIN_QUERY_LENGTH

    if (!shouldSuggestRef.current) {
      setIsLoading(false)
      setHasFetched(false)
      setErrorMessage(null)
      setSuggestions([])
      closeSuggestions()
      return
    }

    if (!hasQuery) {
      setIsLoading(false)
      setHasFetched(false)
      setErrorMessage(null)
      setSuggestions([])
      setActiveIndex(-1)
      if (recentQueries.length > 0 || recommendedQueries.length > 0) {
        setIsOpen(true)
      } else {
        closeSuggestions()
      }
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
  }, [debouncedQuery, closeSuggestions, recentQueries.length, recommendedQueries.length])

  const addRecentQuery = useCallback((value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return
    setRecentQueries((prev) => {
      const deduped = prev.filter((item) => item.toLowerCase() !== trimmed.toLowerCase())
      const next = [trimmed, ...deduped].slice(0, MAX_RECENT)
      saveRecentQueries(next)
      return next
    })
  }, [])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = query.trim()

    suppressSuggestions()

    if (trimmed.length > 0) {
      addRecentQuery(trimmed)
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
    (item: SelectableItem) => {
      const text = item.text.trim()
      if (!text) return
      void postAutocompleteSelect({
        q: query.trim() || undefined,
        text,
        suggest_id: item.suggestion?.suggest_id,
        type: item.suggestion?.type,
        position: item.position,
        source: item.suggestion?.source ?? item.kind,
        target_id: item.suggestion?.target_id,
        target_doc_id: item.suggestion?.target_doc_id,
      })
      setQuery(text)
      addRecentQuery(text)
      suppressSuggestions()
      navigate(`/search?q=${encodeURIComponent(text)}`)
    },
    [addRecentQuery, navigate, query, suppressSuggestions],
  )

  const hasQuery = debouncedQuery.trim().length >= MIN_QUERY_LENGTH
  const suggestionItems: SelectableItem[] = suggestions.map((suggestion, index) => ({
    kind: 'suggestion',
    text: suggestion.text,
    suggestion,
    position: index + 1,
  }))
  const recentItems: SelectableItem[] = recentQueries.map((text, index) => ({
    kind: 'recent',
    text,
    position: index + 1,
  }))
  const recommendedItems: SelectableItem[] = recommendedQueries.map((text, index) => ({
    kind: 'recommended',
    text,
    position: index + 1,
  }))

  const defaultItems = [...recentItems, ...recommendedItems]
  const listItems = hasQuery ? suggestionItems : defaultItems

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const totalItems = listItems.length
    if (event.key === 'Escape') {
      if (isOpen) {
        event.preventDefault()
        suppressSuggestions()
      }
      return
    }

    if (!isOpen && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      if (totalItems > 0) {
        event.preventDefault()
        setIsOpen(true)
        setActiveIndex(event.key === 'ArrowDown' ? 0 : totalItems - 1)
      }
      return
    }

    if (event.key === 'ArrowDown') {
      if (totalItems > 0) {
        event.preventDefault()
        setActiveIndex((prev) => (prev + 1) % totalItems)
      }
      return
    }

    if (event.key === 'ArrowUp') {
      if (totalItems > 0) {
        event.preventDefault()
        setActiveIndex((prev) => (prev <= 0 ? totalItems - 1 : prev - 1))
      }
      return
    }

    if (event.key === 'Enter' && isOpen && activeIndex >= 0) {
      event.preventDefault()
      const item = listItems[activeIndex]
      if (item) {
        handleSelectSuggestion(item)
      }
    }
  }

  const showEmpty = hasQuery && hasFetched && !isLoading && suggestions.length === 0 && !errorMessage
  const showDropdown = isOpen && (isLoading || listItems.length > 0 || showEmpty || Boolean(errorMessage))
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
                <NavLink to="/chat" className={navLinkClassName}>
                  Chat
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
                    if (listItems.length > 0 || showEmpty || errorMessage) {
                      shouldSuggestRef.current = true
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
                    {!isLoading && !errorMessage && listItems.length > 0 ? (
                      <div className="search-suggestion-group">
                        {!hasQuery && recentItems.length > 0 ? (
                          <>
                            <div className="search-suggestion-header">Recent searches</div>
                            {recentItems.map((item, index) => {
                              const globalIndex = index
                              const isActive = globalIndex === activeIndex
                              const itemId = `global-search-option-${globalIndex}`
                              return (
                                <button
                                  key={`recent-${item.text}-${index}`}
                                  id={itemId}
                                  type="button"
                                  role="option"
                                  aria-selected={isActive}
                                  className={`list-group-item list-group-item-action search-suggestion${
                                    isActive ? ' active' : ''
                                  }`}
                                  onClick={() => handleSelectSuggestion(item)}
                                >
                                  <span className="search-suggestion-text">{item.text}</span>
                                  <span className="search-suggestion-meta">Recent</span>
                                </button>
                              )
                            })}
                          </>
                        ) : null}
                        {!hasQuery && recommendedItems.length > 0 ? (
                          <>
                            <div className="search-suggestion-header">Recommended</div>
                            {recommendedItems.map((item, index) => {
                              const offset = recentItems.length
                              const globalIndex = offset + index
                              const isActive = globalIndex === activeIndex
                              const itemId = `global-search-option-${globalIndex}`
                              return (
                                <button
                                  key={`recommended-${item.text}-${index}`}
                                  id={itemId}
                                  type="button"
                                  role="option"
                                  aria-selected={isActive}
                                  className={`list-group-item list-group-item-action search-suggestion${
                                    isActive ? ' active' : ''
                                  }`}
                                  onClick={() => handleSelectSuggestion(item)}
                                >
                                  <span className="search-suggestion-text">{item.text}</span>
                                  <span className="search-suggestion-meta">Recommended</span>
                                </button>
                              )
                            })}
                          </>
                        ) : null}
                        {hasQuery
                          ? suggestionItems.map((item, index) => {
                              const isActive = index === activeIndex
                              const itemId = `global-search-option-${index}`

                              return (
                                <button
                                  key={`${item.text}-${index}`}
                                  id={itemId}
                                  type="button"
                                  role="option"
                                  aria-selected={isActive}
                                  className={`list-group-item list-group-item-action search-suggestion${
                                    isActive ? ' active' : ''
                                  }`}
                                  onClick={() => handleSelectSuggestion(item)}
                                >
                                  <span className="search-suggestion-text">{item.text}</span>
                                  {item.suggestion?.type ? (
                                    <span className="search-suggestion-meta">{item.suggestion.type}</span>
                                  ) : null}
                                </button>
                              )
                            })
                          : null}
                      </div>
                    ) : null}
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

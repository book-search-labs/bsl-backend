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
  '베스트셀러',
  '신간',
  '에세이',
  '자기계발',
  '해리포터',
  '어린이',
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
  const categoryLinks = useMemo(
    () => [
      { label: '베스트셀러', to: '/search?q=베스트셀러' },
      { label: '신간', to: '/search?q=신간' },
      { label: '문학', to: '/search?q=문학' },
      { label: '자기계발', to: '/search?q=자기계발' },
      { label: '경제/경영', to: '/search?q=경제 경영' },
      { label: '어린이', to: '/search?q=어린이' },
      { label: '외국어', to: '/search?q=외국어' },
    ],
    [],
  )

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
        setErrorMessage('추천 검색어 서비스를 사용할 수 없습니다.')
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

  const handleQuickSearch = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      setQuery(trimmed)
      addRecentQuery(trimmed)
      suppressSuggestions()
      navigate(`/search?q=${encodeURIComponent(trimmed)}`)
    },
    [addRecentQuery, navigate, suppressSuggestions],
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
  const utilityLinkClassName = ({ isActive }: { isActive: boolean }) =>
    `utility-link ${isActive ? 'active' : ''}`

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="top-strip">
          <div className="container">
            <div className="top-strip-inner">
              <div className="top-strip-left">
                <span className="top-pill">무료배송</span>
                <span className="top-note">2만원 이상 주문 시</span>
              </div>
              <div className="top-strip-links">
                <span className="top-note">밤 11시 전 주문 시 내일 도착</span>
                <span className="top-divider" />
                <Link to="/about">고객센터</Link>
                <span className="top-divider" />
                <Link to="/orders">주문/배송</Link>
              </div>
            </div>
          </div>
        </div>
        <div className="main-header">
          <div className="container">
            <div className="brand-row">
              <Link to="/" className="brand d-inline-flex align-items-center gap-3">
                <span className="brand-mark">BSL</span>
                <span className="brand-text">
                  <span className="brand-title">BSL Books</span>
                  <span className="brand-subtitle">책 쇼핑 · 검색 · 큐레이션</span>
                </span>
              </Link>
              <div className="search-shell">
                <form ref={formRef} className="search-form search-form--header" onSubmit={handleSubmit}>
                  <label className="visually-hidden" htmlFor="global-search">
                    Search books
                  </label>
                  <div className="typeahead-wrapper">
                    <input
                      id="global-search"
                      className="form-control form-control-lg"
                      type="search"
                      placeholder="도서, 저자, 시리즈, ISBN을 검색하세요"
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
                            <span>추천 검색어를 불러오는 중...</span>
                          </div>
                        ) : null}
                        {!isLoading && errorMessage ? (
                          <div className="list-group-item text-muted small">{errorMessage}</div>
                        ) : null}
                        {!isLoading && !errorMessage && listItems.length > 0 ? (
                          <div className="search-suggestion-group">
                            {!hasQuery && recentItems.length > 0 ? (
                              <>
                                <div className="search-suggestion-header">최근 검색어</div>
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
                                      <span className="search-suggestion-meta">최근</span>
                                    </button>
                                  )
                                })}
                              </>
                            ) : null}
                            {!hasQuery && recommendedItems.length > 0 ? (
                              <>
                                <div className="search-suggestion-header">추천 검색어</div>
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
                                      <span className="search-suggestion-meta">추천</span>
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
                          <div className="list-group-item text-muted small">추천 결과가 없습니다.</div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <button className="btn btn-primary btn-lg search-button" type="submit">
                    검색
                  </button>
                </form>
                <div className="search-meta">
                  <span className="search-meta-label">추천 검색어</span>
                  <div className="search-meta-chips">
                    {recommendedQueries.slice(0, 4).map((text) => (
                      <button
                        key={`quick-${text}`}
                        type="button"
                        className="search-chip"
                        onClick={() => handleQuickSearch(text)}
                      >
                        {text}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="utility-links">
                <NavLink to="/about" className={utilityLinkClassName}>
                  <span className="utility-icon">HELP</span>
                  고객센터
                </NavLink>
                <NavLink to="/cart" className={utilityLinkClassName}>
                  <span className="utility-icon">CART</span>
                  장바구니
                </NavLink>
                <NavLink to="/orders" className={utilityLinkClassName}>
                  <span className="utility-icon">MY</span>
                  주문/배송
                </NavLink>
                <NavLink to="/chat" className={utilityLinkClassName}>
                  <span className="utility-icon">BOT</span>
                  책봇
                </NavLink>
              </div>
            </div>
          </div>
        </div>
        <div className="nav-strip">
          <div className="container">
            <div className="nav-strip-inner">
              <button type="button" className="category-button">
                전체 카테고리
              </button>
              <nav className="category-links">
                {categoryLinks.map((item) => (
                  <Link key={item.label} className="category-link" to={item.to}>
                    {item.label}
                  </Link>
                ))}
                <NavLink to="/search" className={navLinkClassName}>
                  통합검색
                </NavLink>
              </nav>
              <div className="nav-extra">
                <Link to="/search?q=할인" className="nav-extra-link">
                  오늘의 혜택
                </Link>
                <Link to="/search?q=예약" className="nav-extra-link">
                  예약판매
                </Link>
                <Link to="/about" className="nav-extra-link">
                  이용안내
                </Link>
              </div>
            </div>
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

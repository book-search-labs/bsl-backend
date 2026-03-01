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
import { logoutSession } from '../api/auth'
import { getCart } from '../api/cart'
import { fetchKdcCategories, type KdcCategoryNode } from '../api/categories'
import IconNav from '../components/header/IconNav'
import UtilityMenu from '../components/header/UtilityMenu'
import { MY_DROPDOWN_LINKS } from '../components/my/myNavigation'
import FloatingChatWidget from '../components/chat/FloatingChatWidget'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useOutsideClick } from '../hooks/useOutsideClick'
import { clearSession, getSessionId } from '../services/mySession'
import { getTopLevelKdc } from '../utils/kdc'

const AUTOCOMPLETE_SIZE = 8
const AUTOCOMPLETE_DEBOUNCE_MS = 250
const MIN_QUERY_LENGTH = 1
const AUTOCOMPLETE_LISTBOX_ID = 'global-search-suggestions'
const RECENT_STORAGE_KEY = 'bsl.recentSearches'
const MAX_RECENT = 6

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

function resolveEnvRecommendedQueries(): string[] {
  const raw = String(import.meta.env.VITE_AUTOCOMPLETE_RECOMMENDED ?? '')
  return raw
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
}

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([])
  const [recommendedQueries, setRecommendedQueries] = useState<string[]>(() => resolveEnvRecommendedQueries())
  const [recentQueries, setRecentQueries] = useState<string[]>(() => loadRecentQueries())
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [hasFetched, setHasFetched] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [kdcCategories, setKdcCategories] = useState<KdcCategoryNode[]>([])
  const [isCategoryOpen, setIsCategoryOpen] = useState(false)
  const [activeTopCode, setActiveTopCode] = useState<string | null>(null)
  const [cartCount, setCartCount] = useState(0)
  const [myMenuOpen, setMyMenuOpen] = useState(false)
  const [isLoggedIn, setIsLoggedIn] = useState(() => getSessionId() !== null)
  const formRef = useRef<HTMLFormElement>(null)
  const myMenuRef = useRef<HTMLDivElement>(null)
  const shouldSuggestRef = useRef(false)
  const debouncedQuery = useDebouncedValue(query, AUTOCOMPLETE_DEBOUNCE_MS)
  const topCategories = useMemo(() => getTopLevelKdc(kdcCategories), [kdcCategories])
  const categoryLinks = useMemo(() => {
    if (topCategories.length > 0) {
      return topCategories.map((node) => ({
        label: node.name,
        to: `/search?kdc=${encodeURIComponent(node.code)}`,
      }))
    }
    return [
      { label: '베스트셀러', to: '/search?q=베스트셀러' },
      { label: '신간', to: '/search?q=신간' },
      { label: '문학', to: '/search?q=문학' },
      { label: '자기계발', to: '/search?q=자기계발' },
      { label: '경제/경영', to: '/search?q=경제 경영' },
      { label: '어린이', to: '/search?q=어린이' },
      { label: '외국어', to: '/search?q=외국어' },
    ]
  }, [topCategories])

  useEffect(() => {
    if (location.pathname.startsWith('/search')) {
      const nextQuery = searchParams.get('q') ?? ''
      shouldSuggestRef.current = false
      setQuery(nextQuery)
    }
  }, [location.pathname, location.search, searchParams])

  useEffect(() => {
    setIsCategoryOpen(false)
    setMyMenuOpen(false)
    setIsLoggedIn(getSessionId() !== null)
  }, [location.pathname])

  useEffect(() => {
    if (!isLoggedIn) {
      setCartCount(0)
      return
    }

    let active = true
    getCart()
      .then((cart) => {
        if (!active) return
        const nextCount = cart.items.reduce((sum, item) => sum + item.qty, 0)
        setCartCount(nextCount)
      })
      .catch(() => {
        if (active) {
          setCartCount(0)
        }
      })

    return () => {
      active = false
    }
  }, [isLoggedIn, location.pathname])

  const closeSuggestions = useCallback(() => {
    setIsOpen(false)
    setActiveIndex(-1)
  }, [])

  const closeCategoryDrawer = useCallback(() => {
    setIsCategoryOpen(false)
  }, [])

  const openCategoryDrawer = useCallback(() => {
    setIsCategoryOpen(true)
  }, [])

  const closeMyMenu = useCallback(() => {
    setMyMenuOpen(false)
  }, [])

  const toggleMyMenu = useCallback(() => {
    setMyMenuOpen((prev) => !prev)
  }, [])

  const handleLogout = useCallback(() => {
    void logoutSession()
      .catch(() => {
        // ignore logout api failures and clear local session anyway
      })
      .finally(() => {
        clearSession()
        setMyMenuOpen(false)
        setIsLoggedIn(false)
        navigate('/login', { replace: true })
      })
  }, [navigate])

  const handleLogin = useCallback(() => {
    setMyMenuOpen(false)
    const redirect = `${location.pathname}${location.search}`
    navigate(`/login?redirect=${encodeURIComponent(redirect)}`)
  }, [location.pathname, location.search, navigate])

  const activeTopCategory =
    topCategories.find((node) => node.code === activeTopCode) ?? topCategories[0] ?? null

  const handleCategoryNavigate = useCallback(
    (code: string) => {
      if (!code) return
      setIsCategoryOpen(false)
      navigate(`/search?kdc=${encodeURIComponent(code)}`)
    },
    [navigate],
  )

  const suppressSuggestions = useCallback(() => {
    shouldSuggestRef.current = false
    closeSuggestions()
  }, [closeSuggestions])

  useOutsideClick(formRef, () => {
    suppressSuggestions()
  })

  useOutsideClick(myMenuRef, () => {
    closeMyMenu()
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

  const removeRecentQuery = useCallback((value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return
    setRecentQueries((prev) => {
      const next = prev.filter((item) => item.toLowerCase() !== trimmed.toLowerCase())
      saveRecentQueries(next)
      return next
    })
    setActiveIndex(-1)
  }, [])

  const clearRecentQueries = useCallback(() => {
    setRecentQueries([])
    saveRecentQueries([])
    setActiveIndex(-1)
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

  useEffect(() => {
    let active = true
    fetchAutocomplete('', AUTOCOMPLETE_SIZE)
      .then((response) => {
        if (!active) return
        const fromBackend = Array.isArray(response?.suggestions)
          ? response.suggestions
              .map((item) => item.text?.trim())
              .filter((item): item is string => Boolean(item))
          : []
        if (fromBackend.length > 0) {
          setRecommendedQueries(fromBackend.slice(0, MAX_RECENT))
        }
      })
      .catch(() => {
        // keep env fallback
      })

    fetchKdcCategories()
      .then((categories) => {
        if (!active) return
        setKdcCategories(categories)
        if (categories.length > 0) {
          setActiveTopCode(categories[0].code)
        }
      })
      .catch(() => {
        if (active) {
          setKdcCategories([])
        }
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (topCategories.length === 0) return
    if (!activeTopCode || !topCategories.some((node) => node.code === activeTopCode)) {
      setActiveTopCode(topCategories[0].code)
    }
  }, [activeTopCode, topCategories])

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

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="utility-strip">
          <div className="container utility-strip-inner">
            <UtilityMenu isLoggedIn={isLoggedIn} onLogin={handleLogin} onLogout={handleLogout} />
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
                <form
                  ref={formRef}
                  className="search-form search-form--header"
                  onSubmit={handleSubmit}
                  autoComplete="off"
                >
                  <label className="visually-hidden" htmlFor="global-search">
                    Search books
                  </label>
                  <div className="typeahead-wrapper">
                    <input
                      id="global-search"
                      className="form-control form-control-lg"
                      type="text"
                      name="global-search-input"
                      autoComplete="off"
                      autoCorrect="off"
                      autoCapitalize="none"
                      spellCheck={false}
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
                                <div className="search-suggestion-header search-suggestion-header--with-action">
                                  <span>최근 검색어</span>
                                  <button
                                    type="button"
                                    className="search-suggestion-clear"
                                    onMouseDown={(event) => event.preventDefault()}
                                    onClick={clearRecentQueries}
                                  >
                                    전체 삭제
                                  </button>
                                </div>
                                {recentItems.map((item, index) => {
                                  const globalIndex = index
                                  const isActive = globalIndex === activeIndex
                                  const itemId = `global-search-option-${globalIndex}`
                                  return (
                                    <div
                                      key={`recent-${item.text}-${index}`}
                                      className={`list-group-item list-group-item-action search-suggestion${
                                        isActive ? ' active' : ''
                                      } search-suggestion--recent`}
                                    >
                                      <button
                                        id={itemId}
                                        type="button"
                                        role="option"
                                        aria-selected={isActive}
                                        className={`search-suggestion-main${isActive ? ' active' : ''}`}
                                        onClick={() => handleSelectSuggestion(item)}
                                      >
                                        <span className="search-suggestion-text">{item.text}</span>
                                        <span className="search-suggestion-meta">최근</span>
                                      </button>
                                      <button
                                        type="button"
                                        className="search-suggestion-delete"
                                        aria-label={`최근 검색어 ${item.text} 삭제`}
                                        onMouseDown={(event) => event.preventDefault()}
                                        onClick={(event) => {
                                          event.preventDefault()
                                          event.stopPropagation()
                                          removeRecentQuery(item.text)
                                        }}
                                      >
                                        삭제
                                      </button>
                                    </div>
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
              <IconNav
                cartCount={cartCount}
                myMenuOpen={myMenuOpen}
                onToggleMyMenu={toggleMyMenu}
                onCloseMyMenu={closeMyMenu}
                dropdownItems={MY_DROPDOWN_LINKS}
                dropdownRef={myMenuRef}
              />
            </div>
          </div>
        </div>
        <div className="nav-strip">
          <div className="container">
            <div className="nav-strip-inner">
              <button type="button" className="category-button" onClick={openCategoryDrawer}>
                <span className="category-button-icon">|||</span>
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
                <Link to="/benefits" className="nav-extra-link">
                  오늘의 혜택
                </Link>
                <Link to="/preorders" className="nav-extra-link">
                  예약구매
                </Link>
                <Link to="/about" className="nav-extra-link">
                  이용안내
                </Link>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className={`category-drawer ${isCategoryOpen ? 'is-open' : ''}`} aria-hidden={!isCategoryOpen}>
        <div className="category-drawer-backdrop" onClick={closeCategoryDrawer} />
        <div className="category-drawer-panel" role="dialog" aria-modal="true">
          <div className="category-drawer-header">
            <div className="category-drawer-title">카테고리</div>
            <button type="button" className="category-drawer-close" onClick={closeCategoryDrawer}>
              닫기
            </button>
          </div>
          <div className="category-drawer-body">
            <div className="category-column category-column--parents">
              {topCategories.length === 0 ? (
                <div className="category-empty">카테고리를 불러오는 중...</div>
              ) : (
                topCategories.map((node) => (
                  <button
                    key={node.code}
                    type="button"
                    className={`category-parent ${activeTopCategory?.code === node.code ? 'is-active' : ''}`}
                    onClick={() => setActiveTopCode(node.code)}
                  >
                    {node.name}
                  </button>
                ))
              )}
            </div>
            <div className="category-column category-column--children">
              {activeTopCategory ? (
                <>
                  <button
                    type="button"
                    className="category-all"
                    onClick={() => handleCategoryNavigate(activeTopCategory.code)}
                  >
                    {activeTopCategory.name} 전체보기
                  </button>
                  <div className="category-children">
                    {(activeTopCategory.children ?? []).map((child) => (
                      <div key={child.code} className="category-child-group">
                        <button
                          type="button"
                          className="category-child"
                          onClick={() => handleCategoryNavigate(child.code)}
                        >
                          {child.name}
                        </button>
                        {Array.isArray(child.children) && child.children.length > 0 ? (
                          <div className="category-grandchildren">
                            {child.children.map((grand) => (
                              <button
                                key={grand.code}
                                type="button"
                                className="category-grandchild"
                                onClick={() => handleCategoryNavigate(grand.code)}
                              >
                                {grand.name}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="category-empty">카테고리를 불러오는 중...</div>
              )}
            </div>
          </div>
        </div>
      </div>

      <main className="app-main">
        <Outlet context={{ kdcCategories }} />
      </main>
      <FloatingChatWidget />

      <footer className="app-footer mt-auto">
        <div className="app-footer-notice-strip">
          <div className="container app-footer-notice-inner">
            <Link className="app-footer-notice-item" to="/events">
              <strong>공지사항</strong>
              <span>일부 영업점 서비스 종료 안내</span>
            </Link>
            <span className="app-footer-notice-divider" aria-hidden="true">
              |
            </span>
            <Link className="app-footer-notice-item" to="/events">
              <strong>당첨자발표</strong>
              <span>[단독/e캐시] 이벤트 당첨자 발표</span>
            </Link>
          </div>
        </div>

        <div className="container app-footer-inner">
          <div className="app-footer-body">
            <section className="app-footer-company">
              <div className="footer-company-logo">BSL Books</div>
              <nav className="footer-company-links" aria-label="푸터 바로가기">
                <Link to="/about">회사소개</Link>
                <Link to="/events">이용약관</Link>
                <Link to="/my/profile">개인정보처리방침</Link>
                <Link to="/events">청소년보호정책</Link>
                <Link to="/my/support/inquiries">대량구매문의</Link>
                <Link to="/events">채용정보</Link>
                <Link to="/events">광고소개</Link>
              </nav>
              <div className="footer-company-meta">
                <p>(주)BSL Books | 서울특별시 중구 을지로 1 | 대표이사: 홍길동 | 사업자등록번호: 102-81-11670</p>
                <p>대표전화: 1544-1900 | FAX: 0502-987-5711 | 통신판매업신고: 제 653호</p>
                <p>운영시간: 09:00 - 18:00 (주말/공휴일 제외)</p>
              </div>
            </section>

            <section className="app-footer-side">
              <div className="footer-select-row">
                <label className="footer-select-wrap">
                  <span className="visually-hidden">Family site</span>
                  <select
                    className="footer-select"
                    defaultValue=""
                    onChange={(event) => {
                      const targetUrl = event.currentTarget.value
                      if (targetUrl) {
                        window.open(targetUrl, '_blank', 'noopener,noreferrer')
                      }
                      event.currentTarget.value = ''
                    }}
                  >
                    <option value="">Family Site</option>
                    <option value="https://www.booklog.co.kr">북로그</option>
                  </select>
                </label>
                <label className="footer-select-wrap">
                  <span className="visually-hidden">SNS 바로가기</span>
                  <select
                    className="footer-select"
                    defaultValue=""
                    onChange={(event) => {
                      const targetUrl = event.currentTarget.value
                      if (targetUrl) {
                        window.open(targetUrl, '_blank', 'noopener,noreferrer')
                      }
                      event.currentTarget.value = ''
                    }}
                  >
                    <option value="">SNS 바로가기</option>
                    <option value="https://www.instagram.com">Instagram</option>
                    <option value="https://www.youtube.com">YouTube</option>
                    <option value="https://blog.naver.com">Naver Blog</option>
                  </select>
                </label>
              </div>

              <div className="footer-security">
                <div className="footer-security-badge">토스페이먼츠 구매안전서비스</div>
                <p>고객님의 안전한 거래를 위해 결제 보호 서비스를 제공합니다.</p>
              </div>

              <div className="footer-certification">
                <strong>ISMS 인증획득</strong>
                <span>정보보호 관리체계 운영</span>
                <span>유효기간 2023.11.15 ~ 2026.11.14</span>
              </div>
            </section>
          </div>
        </div>

        <div className="app-footer-copy">
          <div className="container app-footer-copy-inner">
            <small>© {new Date().getFullYear()} BSL BOOK CENTRE</small>
          </div>
        </div>
      </footer>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { fetchHomePanels, type HomePanelItem } from '../api/homePanels'
import { formatPanelPeriod, resolvePanelBannerUrl } from '../utils/homePanels'

const EVENT_BANNER_ROTATE_MS = 5500
const PAGE_SIZE = 9

type StatusFilter = 'ONGOING' | 'ENDED' | 'ALL'
type TypeFilter = 'ALL' | 'EVENT' | 'NOTICE'

function parseDate(value?: string | null) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function resolvePanelStatus(item: HomePanelItem, now: Date) {
  const endsAt = parseDate(item.ends_at)
  if (endsAt && endsAt.getTime() < now.getTime()) {
    return 'ENDED' as const
  }
  return 'ONGOING' as const
}

function resolvePanelCategory(item: HomePanelItem) {
  const badge = item.badge?.trim()
  if (badge) return badge
  return item.type === 'NOTICE' ? '공지' : '이벤트'
}

function normalizeText(value?: string | null) {
  if (!value) return ''
  return value.toLowerCase().replace(/\s+/g, ' ').trim()
}

function buildPagination(currentPage: number, totalPages: number): Array<number | 'ellipsis'> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const pages: Array<number | 'ellipsis'> = [1]
  const start = Math.max(2, currentPage - 1)
  const end = Math.min(totalPages - 1, currentPage + 1)

  if (start > 2) {
    pages.push('ellipsis')
  }

  for (let page = start; page <= end; page += 1) {
    pages.push(page)
  }

  if (end < totalPages - 1) {
    pages.push('ellipsis')
  }

  pages.push(totalPages)
  return pages
}

export default function EventsPage() {
  const [panels, setPanels] = useState<HomePanelItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('ALL')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ONGOING')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [currentPage, setCurrentPage] = useState(1)

  useEffect(() => {
    let active = true
    setIsLoading(true)
    setErrorMessage(null)
    fetchHomePanels(200)
      .then((response) => {
        if (!active) return
        setPanels(response.items)
        setActiveIndex(0)
        setIsPaused(false)
      })
      .catch(() => {
        if (!active) return
        setPanels([])
        setErrorMessage('이벤트/공지 정보를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [])

  const categories = useMemo(() => {
    const values = Array.from(new Set(panels.map(resolvePanelCategory).filter((value) => value.length > 0)))
    return values.slice(0, 16)
  }, [panels])

  useEffect(() => {
    if (categories.length === 0) {
      setSelectedCategories([])
      return
    }
    setSelectedCategories((prev) => {
      if (prev.length === 0) return categories
      const next = prev.filter((value) => categories.includes(value))
      return next.length > 0 ? next : categories
    })
  }, [categories])

  useEffect(() => {
    setCurrentPage(1)
  }, [typeFilter, statusFilter, searchKeyword, selectedCategories])

  const filteredPanels = useMemo(() => {
    const now = new Date()
    const keyword = normalizeText(searchKeyword)
    return panels.filter((item) => {
      if (typeFilter !== 'ALL' && item.type !== typeFilter) return false
      const status = resolvePanelStatus(item, now)
      if (statusFilter !== 'ALL' && status !== statusFilter) return false

      const category = resolvePanelCategory(item)
      if (selectedCategories.length > 0 && !selectedCategories.includes(category)) return false

      if (!keyword) return true
      const texts = [
        item.title,
        item.subtitle,
        item.summary,
        item.detail_body,
        item.badge,
        category,
      ]
      return texts.some((text) => normalizeText(text).includes(keyword))
    })
  }, [panels, searchKeyword, selectedCategories, statusFilter, typeFilter])

  const totalPages = Math.max(1, Math.ceil(filteredPanels.length / PAGE_SIZE))
  const safePage = Math.min(Math.max(currentPage, 1), totalPages)

  useEffect(() => {
    if (safePage !== currentPage) {
      setCurrentPage(safePage)
    }
  }, [currentPage, safePage])

  const pageItems = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE
    return filteredPanels.slice(start, start + PAGE_SIZE)
  }, [filteredPanels, safePage])

  const visibleForCarousel = filteredPanels.length > 0 ? filteredPanels : panels

  useEffect(() => {
    if (visibleForCarousel.length <= 1 || isPaused) {
      return
    }
    const timer = window.setInterval(() => {
      setActiveIndex((prev) => (prev + 1) % visibleForCarousel.length)
    }, EVENT_BANNER_ROTATE_MS)
    return () => {
      window.clearInterval(timer)
    }
  }, [isPaused, visibleForCarousel.length])

  useEffect(() => {
    if (visibleForCarousel.length === 0) {
      setActiveIndex(0)
      return
    }
    setActiveIndex((prev) => prev % visibleForCarousel.length)
  }, [visibleForCarousel.length])

  const activePanel = visibleForCarousel.length > 0 ? visibleForCarousel[activeIndex % visibleForCarousel.length] : null
  const canSlide = visibleForCarousel.length > 1
  const displayIndex = visibleForCarousel.length > 0 ? (activeIndex % visibleForCarousel.length) + 1 : 0
  const paginationItems = useMemo(() => buildPagination(safePage, totalPages), [safePage, totalPages])

  const goPrevious = () => {
    if (visibleForCarousel.length === 0) return
    setActiveIndex((prev) => (prev - 1 + visibleForCarousel.length) % visibleForCarousel.length)
  }

  const goNext = () => {
    if (visibleForCarousel.length === 0) return
    setActiveIndex((prev) => (prev + 1) % visibleForCarousel.length)
  }

  const toggleCategory = (category: string) => {
    setSelectedCategories((prev) => {
      if (prev.includes(category)) {
        if (prev.length === 1) return prev
        return prev.filter((value) => value !== category)
      }
      return [...prev, category]
    })
  }

  const resetFilters = () => {
    setTypeFilter('ALL')
    setStatusFilter('ONGOING')
    setSearchKeyword('')
    setSelectedCategories(categories)
    setCurrentPage(1)
  }

  return (
    <section className="events-page page-section">
      <div className="container">
        <h1 className="events-page-title">진행 중인 이벤트를 확인해 보세요</h1>
        <div className="events-carousel-shell">
          {isLoading ? (
            <div className="event-banner-skeleton event-banner-skeleton--single" />
          ) : errorMessage || !activePanel ? (
            <div className="event-panel-empty">{errorMessage ?? '진행 중인 이벤트/공지가 없습니다.'}</div>
          ) : (
            <>
              <Link
                className="event-carousel-link event-carousel-link--center"
                to={`/events/${encodeURIComponent(String(activePanel.item_id))}`}
              >
                <img
                  className="event-banner-image"
                  src={resolvePanelBannerUrl(activePanel)}
                  alt={`${activePanel.type === 'NOTICE' ? '공지' : '이벤트'} 배너`}
                  loading="eager"
                />
              </Link>
              <div className="event-carousel-controls event-carousel-controls--center">
                <button
                  type="button"
                  className="event-control-btn"
                  aria-label="이전 이벤트/공지"
                  onClick={goPrevious}
                  disabled={!canSlide}
                >
                  &lt;
                </button>
                <button
                  type="button"
                  className="event-control-btn"
                  aria-label={isPaused ? '이벤트/공지 자동 넘김 재생' : '이벤트/공지 자동 넘김 정지'}
                  onClick={() => setIsPaused((prev) => !prev)}
                  disabled={!canSlide}
                >
                  {isPaused ? '>' : '||'}
                </button>
                <button
                  type="button"
                  className="event-control-btn"
                  aria-label="다음 이벤트/공지"
                  onClick={goNext}
                  disabled={!canSlide}
                >
                  &gt;
                </button>
                <span className="event-carousel-index">
                  {displayIndex} / {visibleForCarousel.length}
                </span>
              </div>
            </>
          )}
        </div>

        <div className="events-list-layout">
          <aside className="events-filter-sidebar">
            <div className="events-filter-header">
              <h2>필터</h2>
              <button type="button" className="btn btn-link btn-sm p-0" onClick={resetFilters}>
                초기화
              </button>
            </div>

            <div className="events-filter-group">
              <div className="events-filter-group-title">유형</div>
              <button
                type="button"
                className={`events-filter-pill ${typeFilter === 'ALL' ? 'is-active' : ''}`}
                onClick={() => setTypeFilter('ALL')}
              >
                전체
              </button>
              <button
                type="button"
                className={`events-filter-pill ${typeFilter === 'EVENT' ? 'is-active' : ''}`}
                onClick={() => setTypeFilter('EVENT')}
              >
                이벤트
              </button>
              <button
                type="button"
                className={`events-filter-pill ${typeFilter === 'NOTICE' ? 'is-active' : ''}`}
                onClick={() => setTypeFilter('NOTICE')}
              >
                공지
              </button>
            </div>

            <div className="events-filter-group">
              <div className="events-filter-group-title">카테고리</div>
              {categories.map((category) => (
                <label key={category} className="events-check-item">
                  <input
                    type="checkbox"
                    checked={selectedCategories.includes(category)}
                    onChange={() => toggleCategory(category)}
                  />
                  <span>{category}</span>
                </label>
              ))}
            </div>

            <div className="events-filter-group">
              <div className="events-filter-group-title">상태</div>
              <label className="events-check-item">
                <input
                  type="radio"
                  name="event-status"
                  checked={statusFilter === 'ONGOING'}
                  onChange={() => setStatusFilter('ONGOING')}
                />
                <span>진행 중</span>
              </label>
              <label className="events-check-item">
                <input
                  type="radio"
                  name="event-status"
                  checked={statusFilter === 'ENDED'}
                  onChange={() => setStatusFilter('ENDED')}
                />
                <span>종료됨</span>
              </label>
              <label className="events-check-item">
                <input
                  type="radio"
                  name="event-status"
                  checked={statusFilter === 'ALL'}
                  onChange={() => setStatusFilter('ALL')}
                />
                <span>전체</span>
              </label>
            </div>
          </aside>

          <div className="events-list-main">
            <div className="events-list-toolbar">
              <div className="events-list-search">
                <input
                  type="search"
                  value={searchKeyword}
                  onChange={(event) => setSearchKeyword(event.target.value)}
                  placeholder="이벤트명, 공지명으로 검색해 보세요."
                  aria-label="이벤트/공지 검색"
                />
              </div>
              <div className="events-list-count">총 {filteredPanels.length}건</div>
            </div>

            {isLoading ? (
              <div className="event-panel-empty">목록을 불러오는 중입니다...</div>
            ) : errorMessage ? (
              <div className="event-panel-empty">{errorMessage}</div>
            ) : pageItems.length > 0 ? (
              <>
                <div className="events-card-grid">
                  {pageItems.map((item) => (
                    <article key={item.item_id} className="events-card-item">
                      <Link className="events-card-image-link" to={`/events/${encodeURIComponent(String(item.item_id))}`}>
                        <img
                          className="events-card-image"
                          src={resolvePanelBannerUrl(item)}
                          alt={`${item.type === 'NOTICE' ? '공지' : '이벤트'} 배너`}
                          loading="lazy"
                        />
                      </Link>
                      <div className="events-card-body">
                        <div className="events-card-badge">{item.type === 'NOTICE' ? '공지' : '이벤트'}</div>
                        <Link className="events-card-title" to={`/events/${encodeURIComponent(String(item.item_id))}`}>
                          {item.title}
                        </Link>
                        {item.subtitle ? <p className="events-card-subtitle">{item.subtitle}</p> : null}
                        {item.summary ? <p className="events-card-summary">{item.summary}</p> : null}
                        {formatPanelPeriod(item) ? <div className="events-card-period">{formatPanelPeriod(item)}</div> : null}
                      </div>
                    </article>
                  ))}
                </div>

                <nav className="events-pagination" aria-label="이벤트/공지 페이지네이션">
                  <button
                    type="button"
                    className="events-page-btn"
                    onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                    disabled={safePage <= 1}
                  >
                    이전
                  </button>
                  {paginationItems.map((item, index) =>
                    item === 'ellipsis' ? (
                      <span key={`ellipsis-${index}`} className="events-page-ellipsis">
                        ...
                      </span>
                    ) : (
                      <button
                        key={`page-${item}`}
                        type="button"
                        className={`events-page-btn ${safePage === item ? 'is-active' : ''}`}
                        onClick={() => setCurrentPage(item)}
                      >
                        {item}
                      </button>
                    ),
                  )}
                  <button
                    type="button"
                    className="events-page-btn"
                    onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                    disabled={safePage >= totalPages}
                  >
                    다음
                  </button>
                </nav>
              </>
            ) : (
              <div className="event-panel-empty">조건에 맞는 이벤트/공지가 없습니다.</div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

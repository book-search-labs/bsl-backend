import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { Link, useOutletContext } from 'react-router-dom'

import { fetchAutocomplete } from '../api/autocomplete'
import { fetchHomeCollections, type HomeCollectionSection } from '../api/homeCollections'
import { fetchHomePanels, type HomePanelItem } from '../api/homePanels'
import BookCover from '../components/books/BookCover'
import type { KdcCategoryNode } from '../api/categories'
import { clearRecentViews, getRecentViews } from '../utils/recentViews'
import type { RecentView } from '../utils/recentViews'
import { getTopLevelKdc } from '../utils/kdc'
import { resolvePanelBannerUrl } from '../utils/homePanels'

const FALLBACK_CATEGORY_TILES = [
  { label: '베스트셀러', description: '이번 주 인기 도서', query: '베스트셀러' },
  { label: '신간', description: '따끈한 신간 모음', query: '신간' },
  { label: '문학', description: '소설 · 에세이 · 시', query: '문학' },
  { label: '자기계발', description: '커리어 · 성장', query: '자기계발' },
  { label: '경제/경영', description: '비즈니스 인사이트', query: '경제 경영' },
  { label: '어린이', description: '아동 · 청소년', query: '어린이' },
  { label: '외국어', description: '영어 · 일본어', query: '외국어' },
  { label: '취미/실용', description: '라이프스타일', query: '취미' },
]

const HOME_SECTIONS = [
  {
    key: 'bestseller',
    title: '이번 주 베스트셀러',
    note: '지금 가장 많이 찾는 도서를 모았습니다.',
    link: '/collections/bestseller',
  },
  {
    key: 'new',
    title: '신간 · 예약구매',
    note: '곧 출간하는 도서를 예약구매로 먼저 만나보세요.',
    link: '/preorders',
  },
  {
    key: 'editor',
    title: '에디터 추천',
    note: '감성적인 에세이와 문학 작품을 큐레이션했습니다.',
    link: '/collections/editor',
  },
]

const EVENT_BANNER_ROTATE_MS = 5500

const SECTION_DECOR: Record<string, { icon: string; badge: string; tone: string }> = {
  bestseller: { icon: '🔥', badge: '이번 주', tone: 'bestseller' },
  new: { icon: '🆕', badge: '신규', tone: 'new' },
  editor: { icon: '✍️', badge: '큐레이션', tone: 'editor' },
}

function resolveSectionLink(sectionKey: string, serverLink?: string, fallbackLink?: string) {
  if (sectionKey === 'bestseller') {
    return '/collections/bestseller'
  }
  if (sectionKey === 'editor') {
    return '/collections/editor'
  }
  return serverLink ?? fallbackLink ?? '/search'
}

type AppShellContext = {
  kdcCategories: KdcCategoryNode[]
}

function formatAuthors(authors: string[]) {
  return authors.length > 0 ? authors.join(', ') : '저자 정보 없음'
}

function formatViewedAgo(viewedAt: number) {
  if (!Number.isFinite(viewedAt) || viewedAt <= 0) return '방금 확인'
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - viewedAt) / 60000))
  if (elapsedMinutes < 1) return '방금 확인'
  if (elapsedMinutes < 60) return `${elapsedMinutes}분 전`
  const elapsedHours = Math.floor(elapsedMinutes / 60)
  if (elapsedHours < 24) return `${elapsedHours}시간 전`
  const elapsedDays = Math.floor(elapsedHours / 24)
  return `${elapsedDays}일 전`
}

type HorizontalScrollSectionProps = {
  className: string
  itemCount: number
  sliderLabel: string
  children: ReactNode
}

function HorizontalScrollSection({ className, itemCount, sliderLabel, children }: HorizontalScrollSectionProps) {
  const railRef = useRef<HTMLDivElement | null>(null)
  const [sliderMax, setSliderMax] = useState(0)
  const [sliderValue, setSliderValue] = useState(0)

  useEffect(() => {
    const rail = railRef.current
    if (!rail) return

    const updateMetrics = () => {
      const nextMax = Math.max(0, Math.ceil(rail.scrollWidth - rail.clientWidth))
      const nextValue = Math.min(Math.max(0, Math.ceil(rail.scrollLeft)), nextMax)
      setSliderMax(nextMax)
      setSliderValue(nextValue)
    }

    const handleScroll = () => {
      const nextMax = Math.max(0, Math.ceil(rail.scrollWidth - rail.clientWidth))
      const nextValue = Math.min(Math.max(0, Math.ceil(rail.scrollLeft)), nextMax)
      setSliderMax(nextMax)
      setSliderValue(nextValue)
    }

    updateMetrics()
    rail.addEventListener('scroll', handleScroll, { passive: true })
    window.addEventListener('resize', updateMetrics)
    const raf = window.requestAnimationFrame(updateMetrics)

    return () => {
      window.cancelAnimationFrame(raf)
      rail.removeEventListener('scroll', handleScroll)
      window.removeEventListener('resize', updateMetrics)
    }
  }, [itemCount])

  const sliderLimit = Math.max(sliderMax, 1)
  const currentValue = Math.min(sliderValue, sliderLimit)

  const handleSliderChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = Number(event.target.value)
    setSliderValue(nextValue)
    if (!railRef.current) return
    railRef.current.scrollTo({ left: nextValue, behavior: 'auto' })
  }

  return (
    <div className="section-scroll-shell">
      <div ref={railRef} className={className}>
        {children}
      </div>
      <div className="section-scroll-slider-wrap">
        <input
          type="range"
          className="section-scroll-slider"
          min={0}
          max={sliderLimit}
          step={1}
          value={currentValue}
          onChange={handleSliderChange}
          disabled={sliderMax <= 0}
          aria-label={sliderLabel}
        />
      </div>
    </div>
  )
}

export default function HomePage() {
  const sampleQuery = '베스트셀러'
  const sampleLink = `/search?q=${encodeURIComponent(sampleQuery)}`
  const { kdcCategories } = useOutletContext<AppShellContext>()
  const topCategories = useMemo(() => getTopLevelKdc(kdcCategories), [kdcCategories])
  const categoryTiles =
    topCategories.length > 0
      ? topCategories.map((node) => ({
          label: node.name,
          description: `KDC ${node.code}`,
          to: `/search?kdc=${encodeURIComponent(node.code)}`,
        }))
      : FALLBACK_CATEGORY_TILES.map((tile) => ({
          ...tile,
          to: `/search?q=${encodeURIComponent(tile.query)}`,
        }))
  const [recentViews, setRecentViews] = useState<RecentView[]>([])
  const [trendingQueries, setTrendingQueries] = useState<string[]>([])
  const [homePanels, setHomePanels] = useState<HomePanelItem[]>([])
  const [homePanelLoading, setHomePanelLoading] = useState(true)
  const [homePanelError, setHomePanelError] = useState<string | null>(null)
  const [activePanelIndex, setActivePanelIndex] = useState(0)
  const [isPanelPaused, setIsPanelPaused] = useState(false)
  const [homeSections, setHomeSections] = useState<HomeCollectionSection[]>(
    HOME_SECTIONS.map((section) => ({
      key: section.key,
      title: section.title,
      note: section.note,
      link: resolveSectionLink(section.key, undefined, section.link),
      items: [],
    })),
  )
  const [homeSectionsLoading, setHomeSectionsLoading] = useState(true)
  const [homeSectionsError, setHomeSectionsError] = useState<string | null>(null)

  useEffect(() => {
    setRecentViews(getRecentViews().slice(0, 6))
  }, [])

  useEffect(() => {
    let active = true
    fetchAutocomplete('', 8)
      .then((response) => {
        if (!active) return
        const queries = Array.isArray(response?.suggestions)
          ? response.suggestions
              .map((item) => item.text?.trim())
              .filter((item): item is string => Boolean(item))
          : []
        setTrendingQueries(queries.slice(0, 8))
      })
      .catch(() => {
        if (active) {
          setTrendingQueries([])
        }
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    setHomePanelLoading(true)
    setHomePanelError(null)

    fetchHomePanels(31)
      .then((response) => {
        if (!active) return
        setHomePanels(response.items)
        setActivePanelIndex(0)
        setIsPanelPaused(false)
      })
      .catch(() => {
        if (!active) return
        setHomePanels([])
        setActivePanelIndex(0)
        setHomePanelError('이벤트/공지 정보를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) {
          setHomePanelLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (homePanels.length <= 1 || isPanelPaused) {
      return
    }
    const timer = window.setInterval(() => {
      setActivePanelIndex((prev) => (prev + 1) % homePanels.length)
    }, EVENT_BANNER_ROTATE_MS)
    return () => {
      window.clearInterval(timer)
    }
  }, [homePanels.length, isPanelPaused])

  useEffect(() => {
    let active = true

    setHomeSectionsLoading(true)
    setHomeSectionsError(null)

    fetchHomeCollections(8)
      .then((response) => {
        if (!active) return
        const byKey = new Map((response.sections ?? []).map((section) => [section.key, section]))
        const merged = HOME_SECTIONS.map((section) => {
          const server = byKey.get(section.key)
          return {
            key: section.key,
            title: server?.title ?? section.title,
            note: server?.note ?? section.note,
            link: resolveSectionLink(section.key, server?.link, section.link),
            items: Array.isArray(server?.items) ? server.items : [],
          }
        })
        setHomeSections(merged)
      })
      .catch(() => {
        if (!active) return
        setHomeSections(
          HOME_SECTIONS.map((section) => ({
            key: section.key,
            title: section.title,
            note: section.note,
            link: resolveSectionLink(section.key, undefined, section.link),
            items: [],
          })),
        )
        setHomeSectionsError('추천 도서를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) {
          setHomeSectionsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [])

  const handleClear = () => {
    clearRecentViews()
    setRecentViews([])
  }

  const recentLinks = useMemo(() => {
    return recentViews.map((item) => ({
      ...item,
      to: `/book/${encodeURIComponent(item.docId)}?from=recent`,
    }))
  }, [recentViews])

  const activePanel = homePanels.length > 0 ? homePanels[activePanelIndex % homePanels.length] : null
  const activePanelDisplayIndex = homePanels.length > 0 ? (activePanelIndex % homePanels.length) + 1 : 0
  const canSlidePanels = homePanels.length > 1
  const moveToPreviousPanel = () => {
    if (homePanels.length === 0) return
    setActivePanelIndex((prev) => (prev - 1 + homePanels.length) % homePanels.length)
  }
  const moveToNextPanel = () => {
    if (homePanels.length === 0) return
    setActivePanelIndex((prev) => (prev + 1) % homePanels.length)
  }

  return (
    <section className="home-page">
      <div className="home-hero">
        <div className="container">
          <div className="hero-grid hero-grid--banner-only">
            <div className="hero-panels hero-panels--full">
              <div className="event-panel" aria-label="이벤트/공지 배너">
                <div className="event-panel-toolbar">
                  <Link className="event-panel-button" to="/events">
                    이벤트/공지
                  </Link>
                </div>
                {homePanelLoading ? (
                  <div className="event-banner-skeleton event-banner-skeleton--single" aria-label="이벤트 배너 로딩" />
                ) : homePanelError || !activePanel ? (
                  <div className="event-panel-empty">{homePanelError ?? '진행 중인 이벤트/공지가 없습니다.'}</div>
                ) : (
                  <>
                    <Link className="event-carousel-link" to={`/events/${encodeURIComponent(String(activePanel.item_id))}`}>
                      <img
                        className="event-banner-image"
                        src={resolvePanelBannerUrl(activePanel)}
                        alt={`${activePanel.type === 'NOTICE' ? '공지' : '이벤트'} 배너`}
                        loading="eager"
                      />
                    </Link>
                    <div className="event-carousel-controls">
                      <button
                        type="button"
                        className="event-control-btn"
                        aria-label="이전 이벤트/공지"
                        onClick={moveToPreviousPanel}
                        disabled={!canSlidePanels}
                      >
                        &lt;
                      </button>
                      <button
                        type="button"
                        className="event-control-btn"
                        aria-label={isPanelPaused ? '이벤트/공지 자동 넘김 재생' : '이벤트/공지 자동 넘김 정지'}
                        onClick={() => setIsPanelPaused((prev) => !prev)}
                        disabled={!canSlidePanels}
                      >
                        {isPanelPaused ? '>' : '||'}
                      </button>
                      <button
                        type="button"
                        className="event-control-btn"
                        aria-label="다음 이벤트/공지"
                        onClick={moveToNextPanel}
                        disabled={!canSlidePanels}
                      >
                        &gt;
                      </button>
                      <span className="event-carousel-index">
                        {activePanelDisplayIndex} / {homePanels.length}
                      </span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="home-feature-strip">
        <div className="container">
          <div className="feature-grid">
            <div className="feature-card">
              <div className="feature-title">빠른 배송</div>
              <p className="feature-meta">오늘 밤 11시 전 주문하면 내일 받아보세요.</p>
            </div>
            <div className="feature-card">
              <div className="feature-title">안심 반품</div>
              <p className="feature-meta">7일 내 무료 반품 정책을 지원합니다.</p>
            </div>
            <div className="feature-card">
              <div className="feature-title">맞춤 추천</div>
              <p className="feature-meta">최근 본 책을 기반으로 큐레이션해드립니다.</p>
            </div>
          </div>
        </div>
      </div>

      <div className="home-category-strip">
        <div className="container">
          <div className="category-grid">
            {categoryTiles.map((category) => (
              <Link
                key={category.label}
                to={category.to}
                className="category-card"
              >
                <span className="category-card-title">{category.label}</span>
                <span className="category-card-note">{category.description}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="container home-feed-layout">
        <div className="home-feed-main">
          <div className="home-block home-block--trend">
            <div className="home-block-header">
              <div>
                <p className="section-kicker">트렌드</p>
                <h2 className="section-title">지금 많이 찾는 키워드</h2>
                <p className="section-note">인기 검색어와 추천 흐름을 빠르게 확인하세요.</p>
              </div>
              <Link to="/search" className="section-link-btn">
                통합검색
              </Link>
            </div>
            <HorizontalScrollSection
              className="trend-rank-grid"
              itemCount={Math.max(trendingQueries.length, 8)}
              sliderLabel="지금 많이 찾는 키워드 슬라이드"
            >
              {trendingQueries.length > 0
                ? trendingQueries.map((query, index) => (
                    <Link key={query} to={`/search?q=${encodeURIComponent(query)}`} className="trend-rank-card">
                      <span className="trend-rank-no">{String(index + 1).padStart(2, '0')}</span>
                      <span className="trend-rank-text">{query}</span>
                      <span className={`trend-rank-state ${index < 3 ? 'up' : 'steady'}`}>
                        {index < 3 ? '급상승' : '인기'}
                      </span>
                    </Link>
                  ))
                : Array.from({ length: 8 }).map((_, index) => (
                    <div key={`trend-skeleton-${index}`} className="trend-rank-card trend-rank-card--skeleton" />
                  ))}
            </HorizontalScrollSection>
          </div>

          {homeSections.map((section) => {
            const hits = Array.isArray(section.items) ? section.items : []
            const decor = SECTION_DECOR[section.key] ?? { icon: '📚', badge: '컬렉션', tone: 'default' }
            return (
              <div key={section.key} className={`home-block home-block--${decor.tone}`}>
                <div className="home-block-header">
                  <div>
                    <div className="section-title-row">
                      <span className={`section-badge section-badge--${decor.tone}`}>{decor.badge}</span>
                      <h2 className="section-title section-title--with-icon">
                        <span className="section-title-icon" aria-hidden="true">
                          {decor.icon}
                        </span>
                        {section.title}
                      </h2>
                    </div>
                    <p className="section-note">{section.note}</p>
                  </div>
                  <Link to={section.link ?? '/search'} className="section-link-btn">
                    전체 보기
                  </Link>
                </div>
                {homeSectionsError ? (
                  <div className="placeholder-card empty-state">
                    <div className="empty-title">추천 도서를 불러오지 못했습니다</div>
                    <div className="empty-copy">잠시 후 다시 시도해주세요.</div>
                  </div>
                ) : (
                  <HorizontalScrollSection
                    className="shelf-row"
                    itemCount={homeSectionsLoading || hits.length === 0 ? 6 : hits.length}
                    sliderLabel={`${section.title} 슬라이드`}
                  >
                    {homeSectionsLoading || hits.length === 0
                      ? Array.from({ length: 6 }).map((_, index) => (
                          <article key={`skeleton-${section.key}-${index}`} className="book-tile book-tile--compact skeleton" />
                        ))
                      : hits.map((hit, index) => {
                          const title = hit.title_ko ?? '제목 없음'
                          const authors = Array.isArray(hit.authors) ? hit.authors : []
                          const publisher = hit.publisher_name ?? '출판사 정보 없음'
                          const year = hit.issued_year ?? '-'
                          const docId = hit.doc_id
                          const detailLink = docId
                            ? `/book/${encodeURIComponent(docId)}?from=home`
                            : `/search?q=${encodeURIComponent(title)}`
                          const searchLink = (() => {
                            const params = new URLSearchParams()
                            params.set('q', title)
                            params.set('vector', 'true')
                            params.set('related_title', title)
                            if (docId) {
                              params.set('related', docId)
                            }
                            return `/search?${params.toString()}`
                          })()
                          const labels = Array.isArray(hit.edition_labels)
                            ? hit.edition_labels.slice(0, 2)
                            : []

                          return (
                            <article key={docId ?? `${section.key}-${index}`} className="book-tile book-tile--compact">
                              <Link
                                className={`book-tile-cover book-tile-cover-link book-tile-cover--${decor.tone}`}
                                to={detailLink}
                                aria-label={`${title} 상세보기`}
                              >
                                <BookCover
                                  className="book-cover-image"
                                  title={title}
                                  coverUrl={typeof hit.cover_url === 'string' ? hit.cover_url : null}
                                  isbn13={typeof hit.isbn13 === 'string' ? hit.isbn13 : null}
                                  docId={docId ?? null}
                                  size="M"
                                />
                                <span className="book-tile-rank">#{index + 1}</span>
                              </Link>
                              <div className="book-tile-body">
                                <h3 className="book-tile-title">{title}</h3>
                                <p className="book-tile-meta">{formatAuthors(authors)}</p>
                                <p className="book-tile-meta">{publisher} · {year}</p>
                                <div className="book-tile-tags">
                                  {labels.length > 0 ? (
                                    labels.map((label) => (
                                      <span key={label} className="tag-chip">
                                        {label}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="tag-chip muted">판형 정보 없음</span>
                                  )}
                                </div>
                                <div className="book-tile-actions">
                                  <Link className="btn btn-outline-dark btn-sm" to={detailLink}>
                                    상세보기
                                  </Link>
                                  <Link className="btn btn-outline-secondary btn-sm" to={searchLink}>
                                    비슷한 책
                                  </Link>
                                </div>
                              </div>
                            </article>
                          )
                        })}
                  </HorizontalScrollSection>
                )}
              </div>
            )
          })}
        </div>

        <aside className="home-feed-side">
          <div className="home-block side-block">
            <div className="home-block-header">
              <div>
                <h2 className="section-title">최근 본 도서</h2>
                <p className="section-note">방금 확인한 책을 바로 이어서 보세요.</p>
              </div>
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={handleClear}
                disabled={recentViews.length === 0}
              >
                기록 삭제
              </button>
            </div>
            {recentLinks.length > 0 ? (
              <div className="recent-list">
                {recentLinks.map((item) => (
                  <Link key={item.docId} to={item.to} className="recent-card">
                    <BookCover
                      className="recent-card-cover"
                      title={item.titleKo}
                      coverUrl={item.coverUrl ?? null}
                      isbn13={item.isbn13 ?? null}
                      docId={item.docId}
                      size="S"
                    />
                    <div className="recent-card-body">
                      <div className="recent-card-title">{item.titleKo ?? '제목 없음'}</div>
                      <div className="recent-card-meta">{formatAuthors(item.authors)}</div>
                      <div className="recent-card-time">{formatViewedAgo(item.viewedAt)}</div>
                    </div>
                    <span className="recent-card-cta">이어보기</span>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="placeholder-card empty-state">
                <div className="empty-title">최근 본 도서가 없습니다</div>
                <div className="empty-copy">지금 베스트셀러를 둘러보세요.</div>
                <Link to={sampleLink} className="btn btn-outline-dark btn-sm">
                  베스트셀러 보기
                </Link>
              </div>
            )}
          </div>
        </aside>
      </div>

      <div className="container home-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">필요한 정보를 빠르게</h2>
            <p className="section-note">배송, 환불, 주문 문의를 빠르게 이동하세요.</p>
          </div>
          <Link to="/chat" className="section-link-btn">
            책봇 상담
          </Link>
        </div>
        <div className="help-grid">
          <div className="help-card">
            <div className="help-title">배송/반품 안내</div>
            <p className="help-meta">주문 후 배송 상황과 반품 정책을 확인하세요.</p>
            <Link to="/about" className="help-link">
              자세히 보기
            </Link>
          </div>
          <div className="help-card">
            <div className="help-title">주문 내역 확인</div>
            <p className="help-meta">주문 상태와 결제 내역을 확인하세요.</p>
            <Link to="/orders" className="help-link">
              주문/배송 보기
            </Link>
          </div>
          <div className="help-card">
            <div className="help-title">장바구니 바로가기</div>
            <p className="help-meta">담아둔 도서를 한 번에 결제하세요.</p>
            <Link to="/cart" className="help-link">
              장바구니 열기
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { search } from '../api/searchApi'
import type { BookHit } from '../types/search'
import { clearRecentViews, getRecentViews } from '../utils/recentViews'
import type { RecentView } from '../utils/recentViews'

const HERO_STATS = [
  { label: '빠른 배송', value: '내일 도착' },
  { label: '도서 데이터', value: '1.2M+' },
  { label: '고객 만족', value: '4.8/5' },
]

const CATEGORY_TILES = [
  { label: '베스트셀러', description: '이번 주 인기 도서', query: '베스트셀러' },
  { label: '신간', description: '따끈한 신간 모음', query: '신간' },
  { label: '문학', description: '소설 · 에세이 · 시', query: '문학' },
  { label: '자기계발', description: '커리어 · 성장', query: '자기계발' },
  { label: '경제/경영', description: '비즈니스 인사이트', query: '경제 경영' },
  { label: '어린이', description: '아동 · 청소년', query: '어린이' },
  { label: '외국어', description: '영어 · 일본어', query: '외국어' },
  { label: '취미/실용', description: '라이프스타일', query: '취미' },
]

const TRENDING_QUERIES = ['해리포터', '에세이', 'UX 디자인', '투자 입문', '아이와 읽는 책', '일러스트']

const HOME_SECTIONS = [
  {
    key: 'bestseller',
    title: '이번 주 베스트셀러',
    note: '지금 가장 많이 찾는 도서를 모았습니다.',
    query: '베스트셀러',
    link: '/search?q=베스트셀러',
  },
  {
    key: 'new',
    title: '신간 · 예약 판매',
    note: '새로운 출간 소식을 가장 먼저 만나보세요.',
    query: '신간',
    link: '/search?q=신간',
  },
  {
    key: 'editor',
    title: '에디터 추천',
    note: '감성적인 에세이와 문학 작품을 큐레이션했습니다.',
    query: '에세이',
    link: '/search?q=에세이',
  },
]

type SectionState = {
  hits: BookHit[]
  isLoading: boolean
  error?: string
}

function buildInitialSectionState() {
  return HOME_SECTIONS.reduce((acc, section) => {
    acc[section.key] = { hits: [], isLoading: true }
    return acc
  }, {} as Record<string, SectionState>)
}

function formatAuthors(authors: string[]) {
  return authors.length > 0 ? authors.join(', ') : '저자 정보 없음'
}

export default function HomePage() {
  const sampleQuery = '베스트셀러'
  const sampleLink = `/search?q=${encodeURIComponent(sampleQuery)}`
  const [recentViews, setRecentViews] = useState<RecentView[]>([])
  const [sectionState, setSectionState] = useState<Record<string, SectionState>>(() =>
    buildInitialSectionState(),
  )

  useEffect(() => {
    setRecentViews(getRecentViews().slice(0, 6))
  }, [])

  useEffect(() => {
    let active = true

    HOME_SECTIONS.forEach((section) => {
      search(section.query, { size: 8, from: 0, vector: true })
        .then((response) => {
          if (!active) return
          setSectionState((prev) => ({
            ...prev,
            [section.key]: {
              hits: Array.isArray(response.hits) ? response.hits : [],
              isLoading: false,
            },
          }))
        })
        .catch(() => {
          if (!active) return
          setSectionState((prev) => ({
            ...prev,
            [section.key]: {
              hits: [],
              isLoading: false,
              error: '추천 도서를 불러오지 못했습니다.',
            },
          }))
        })
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

  return (
    <section className="home-page">
      <div className="home-hero">
        <div className="container">
          <div className="hero-grid">
            <div className="hero-copy">
              <p className="hero-badge">BOOK COMMERCE</p>
              <h1 className="hero-title">지금 필요한 책, 더 빠르고 믿을 수 있게</h1>
              <p className="hero-lead">
                BSL 검색 기술과 커머스 경험을 결합해, 원하는 책을 빠르게 찾고 안전하게
                주문할 수 있습니다.
              </p>
              <div className="hero-actions">
                <Link className="btn btn-primary btn-lg" to={sampleLink}>
                  베스트셀러 보러가기
                </Link>
                <Link className="btn btn-outline-secondary btn-lg" to="/search">
                  통합검색
                </Link>
              </div>
              <div className="hero-stats">
                {HERO_STATS.map((stat) => (
                  <div key={stat.label} className="hero-stat">
                    <span className="hero-stat-number">{stat.value}</span>
                    <span className="hero-stat-label">{stat.label}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="hero-panels">
              <div className="promo-card promo-card--strong">
                <span className="promo-tag">이번 주 혜택</span>
                <span className="promo-title">멤버십 전용 가격 + 무료배송</span>
                <span className="promo-meta">장바구니에서 멤버십 혜택을 확인하세요.</span>
                <span className="promo-link">혜택 보기</span>
              </div>
              <div className="promo-card">
                <span className="promo-tag">추천 컬렉션</span>
                <span className="promo-title">감성 에세이 베스트 10</span>
                <span className="promo-meta">하루를 채우는 따뜻한 문장들</span>
                <Link className="promo-link" to="/search?q=에세이">
                  바로가기
                </Link>
              </div>
              <div className="promo-card">
                <span className="promo-tag">AI 큐레이션</span>
                <span className="promo-title">책봇에게 추천을 받아보세요</span>
                <span className="promo-meta">읽고 싶은 분위기를 말하면 추천해드려요.</span>
                <Link className="promo-link" to="/chat">
                  책봇 열기
                </Link>
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
            {CATEGORY_TILES.map((category) => (
              <Link
                key={category.label}
                to={`/search?q=${encodeURIComponent(category.query)}`}
                className="category-card"
              >
                <span className="category-card-title">{category.label}</span>
                <span className="category-card-note">{category.description}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="container home-section">
        <div className="section-header">
          <div>
            <p className="section-kicker">트렌드</p>
            <h2 className="section-title">지금 많이 찾는 키워드</h2>
            <p className="section-note">인기 검색어로 빠르게 탐색하세요.</p>
          </div>
        </div>
        <div className="chip-list">
          {TRENDING_QUERIES.map((query) => (
            <Link key={query} to={`/search?q=${encodeURIComponent(query)}`} className="trend-chip">
              {query}
            </Link>
          ))}
        </div>
      </div>

      {HOME_SECTIONS.map((section) => {
        const state = sectionState[section.key]
        return (
          <div key={section.key} className="container home-section">
            <div className="section-header">
              <div>
                <h2 className="section-title">{section.title}</h2>
                <p className="section-note">{section.note}</p>
              </div>
              <Link to={section.link} className="section-link">
                전체 보기
              </Link>
            </div>
            {state?.isLoading ? (
              <div className="shelf-grid">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={`skeleton-${section.key}-${index}`} className="book-tile skeleton" />
                ))}
              </div>
            ) : state?.error ? (
              <div className="placeholder-card empty-state">
                <div className="empty-title">추천 도서를 불러오지 못했습니다</div>
                <div className="empty-copy">잠시 후 다시 시도해주세요.</div>
              </div>
            ) : (
              <div className="shelf-grid">
                {(state?.hits ?? []).map((hit, index) => {
                  const source = hit.source ?? {}
                  const title = source.title_ko ?? '제목 없음'
                  const authors = Array.isArray(source.authors) ? source.authors : []
                  const publisher = source.publisher_name ?? '출판사 정보 없음'
                  const year = source.issued_year ?? '-'
                  const docId = hit.doc_id
                  const detailLink = docId
                    ? `/book/${encodeURIComponent(docId)}?from=home`
                    : `/search?q=${encodeURIComponent(title)}`
                  const searchLink = `/search?q=${encodeURIComponent(title)}`
                  const labels = Array.isArray(source.edition_labels)
                    ? source.edition_labels.slice(0, 2)
                    : []

                  return (
                    <article key={docId ?? `${section.key}-${index}`} className="book-tile">
                      <div className="book-tile-cover">
                        <span className="book-tile-rank">#{index + 1}</span>
                        <span className="book-tile-cover-title">{title}</span>
                      </div>
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
              </div>
            )}
          </div>
        )
      })}

      <div className="container home-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">최근 본 도서</h2>
            <p className="section-note">최근에 확인한 책을 다시 찾아보세요.</p>
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
          <div className="recent-grid">
            {recentLinks.map((item) => (
              <Link key={item.docId} to={item.to} className="recent-card">
                <div className="recent-card-title">{item.titleKo ?? 'Untitled'}</div>
                <div className="recent-card-meta">{formatAuthors(item.authors)}</div>
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

      <div className="container home-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">필요한 정보를 빠르게</h2>
            <p className="section-note">배송, 환불, 주문 문의는 책봇이 도와드립니다.</p>
          </div>
          <Link to="/chat" className="section-link">
            책봇 상담하기
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
            <p className="help-meta">주문 상태, 결제 내역을 관리할 수 있어요.</p>
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

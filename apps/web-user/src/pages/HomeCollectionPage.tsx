import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { fetchHomeCollections, type HomeCollectionItem, type HomeCollectionSection } from '../api/homeCollections'
import BookCover from '../components/books/BookCover'

const LIMIT_PER_SECTION = 24

type SectionMeta = {
  title: string
  note: string
  badge: string
  fallbackLink: string
}

const SECTION_META: Record<string, SectionMeta> = {
  bestseller: {
    title: '이번 주 베스트셀러',
    note: '지금 가장 많이 찾는 도서를 모았습니다.',
    badge: '이번 주 인기',
    fallbackLink: '/search?q=베스트셀러',
  },
  editor: {
    title: '에디터 추천',
    note: '감성적인 에세이와 문학 작품을 큐레이션했습니다.',
    badge: '큐레이션 추천',
    fallbackLink: '/search?kdc=800',
  },
  new: {
    title: '신간 · 예약구매',
    note: '곧 출간하는 도서를 예약구매로 먼저 만나보세요.',
    badge: '신규 컬렉션',
    fallbackLink: '/search?q=신간',
  },
}

function formatAuthors(authors: string[]) {
  return authors.length > 0 ? authors.join(', ') : '저자 정보 없음'
}

function formatIssuedYear(year?: number) {
  if (typeof year !== 'number' || !Number.isFinite(year)) return '-'
  return String(year)
}

function isSupportedSection(sectionKey: string) {
  return sectionKey === 'bestseller' || sectionKey === 'editor' || sectionKey === 'new'
}

function asSectionItems(section: HomeCollectionSection | null) {
  return Array.isArray(section?.items) ? section.items : []
}

function resolveMeta(sectionKey: string): SectionMeta {
  return SECTION_META[sectionKey] ?? {
    title: '컬렉션',
    note: '추천 도서를 모아볼 수 있어요.',
    badge: '추천',
    fallbackLink: '/search',
  }
}

function getDetailLink(item: HomeCollectionItem) {
  const docId = typeof item.doc_id === 'string' ? item.doc_id.trim() : ''
  if (!docId) return null
  return `/book/${encodeURIComponent(docId)}?from=collection`
}

export default function HomeCollectionPage() {
  const params = useParams()
  const sectionKey = (params.sectionKey ?? '').trim().toLowerCase()
  const supported = isSupportedSection(sectionKey)

  const [section, setSection] = useState<HomeCollectionSection | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const meta = useMemo(() => resolveMeta(sectionKey), [sectionKey])
  const items = useMemo(() => asSectionItems(section), [section])
  const sectionTitle = section?.title ?? meta.title
  const sectionNote = section?.note ?? meta.note
  const fallbackSearchLink = meta.fallbackLink

  useEffect(() => {
    if (!supported) {
      setSection(null)
      setError(null)
      setLoading(false)
      return
    }

    let active = true
    setLoading(true)
    setError(null)

    fetchHomeCollections(LIMIT_PER_SECTION)
      .then((response) => {
        if (!active) return
        const matched = response.sections.find((entry) => (entry.key ?? '').trim().toLowerCase() === sectionKey) ?? null
        setSection(matched)
      })
      .catch(() => {
        if (!active) return
        setSection(null)
        setError('컬렉션을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.')
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [sectionKey, supported])

  if (!supported) {
    return (
      <section className="page-section">
        <div className="container py-4">
          <div className="alert alert-warning" role="status">
            <p className="mb-2 fw-semibold">지원하지 않는 컬렉션입니다.</p>
            <div className="d-flex gap-2">
              <Link to="/" className="btn btn-outline-dark btn-sm">
                홈으로
              </Link>
              <Link to="/search" className="btn btn-outline-secondary btn-sm">
                통합검색
              </Link>
            </div>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="home-collection-page preorders-page page-section">
      <div className="container">
        <header className="preorders-header">
          <h1 className="preorders-title">{sectionTitle} 전체보기</h1>
          <p className="preorders-note">{sectionNote}</p>
        </header>

        <div className="home-collection-actions">
          <Link to="/" className="btn btn-outline-secondary btn-sm">
            홈으로
          </Link>
          <Link to={fallbackSearchLink} className="btn btn-outline-dark btn-sm">
            검색 결과 보기
          </Link>
        </div>

        {loading ? (
          <div className="preorder-grid home-collection-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <article key={`collection-skeleton-${index}`} className="preorder-card preorder-card--skeleton" />
            ))}
          </div>
        ) : error ? (
          <div className="event-panel-empty">{error}</div>
        ) : items.length === 0 ? (
          <div className="event-panel-empty">현재 노출할 도서가 없습니다.</div>
        ) : (
          <div className="preorder-grid home-collection-grid">
            {items.map((item, index) => {
              const title = item.title_ko ?? '제목 없음'
              const detailLink = getDetailLink(item)
              const searchLink = `/search?q=${encodeURIComponent(title)}`
              const labels = Array.isArray(item.edition_labels) ? item.edition_labels.slice(0, 2) : []
              const editionSummary = labels.length > 0 ? labels.join(' · ') : '판형 정보 없음'

              return (
                <article key={item.doc_id ?? `${sectionKey}-${index}`} className="preorder-card home-collection-card">
                  <div className="preorder-cover-wrap">
                    {detailLink ? (
                      <Link to={detailLink}>
                        <BookCover
                          className="preorder-cover"
                          title={title}
                          coverUrl={typeof item.cover_url === 'string' ? item.cover_url : null}
                          isbn13={typeof item.isbn13 === 'string' ? item.isbn13 : null}
                          docId={typeof item.doc_id === 'string' ? item.doc_id : null}
                          size="M"
                        />
                      </Link>
                    ) : (
                      <BookCover
                        className="preorder-cover"
                        title={title}
                        coverUrl={typeof item.cover_url === 'string' ? item.cover_url : null}
                        isbn13={typeof item.isbn13 === 'string' ? item.isbn13 : null}
                        docId={typeof item.doc_id === 'string' ? item.doc_id : null}
                        size="M"
                      />
                    )}
                    <span className="preorder-badge">{meta.badge}</span>
                  </div>

                  <div className="preorder-body">
                    <h2 className="preorder-book-title">{title}</h2>
                    <p className="preorder-book-meta">{formatAuthors(Array.isArray(item.authors) ? item.authors : [])}</p>
                    <p className="preorder-book-meta">{item.publisher_name ?? '출판사 정보 없음'}</p>
                    <div className="preorder-window">발행 {formatIssuedYear(item.issued_year)}</div>
                    <div className="preorder-remaining">{editionSummary}</div>
                    <div className="preorder-actions">
                      <Link to={detailLink ?? searchLink} className="btn btn-outline-dark btn-sm">
                        상세보기
                      </Link>
                      <Link to={searchLink} className="btn btn-outline-secondary btn-sm">
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
    </section>
  )
}

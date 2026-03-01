import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import BookCover from '../components/books/BookCover'
import { fetchPreorders, reservePreorder, type PreorderItem } from '../api/preorders'

function formatDateLabel(iso?: string | null) {
  if (!iso) return '-'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '-'
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`
}

function formatAuthors(authors: string[] | undefined) {
  if (!Array.isArray(authors) || authors.length === 0) return '저자 정보 없음'
  return authors.join(', ')
}

export default function PreordersPage() {
  const [items, setItems] = useState<PreorderItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [processingId, setProcessingId] = useState<number | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setIsLoading(true)
    setErrorMessage(null)
    fetchPreorders(24)
      .then((result) => {
        if (!active) return
        setItems(result.items)
      })
      .catch(() => {
        if (!active) return
        setItems([])
        setErrorMessage('예약구매 상품을 불러오지 못했습니다.')
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

  const activeItems = useMemo(() => items.slice(0, 12), [items])

  const handleReserve = async (item: PreorderItem) => {
    if (!item.preorder_id) return
    setProcessingId(item.preorder_id)
    setActionMessage(null)
    try {
      const reservation = await reservePreorder(item.preorder_id, 1)
      setItems((prev) =>
        prev.map((entry) =>
          entry.preorder_id === item.preorder_id
            ? {
                ...entry,
                reserved_by_me: true,
                reserved_qty: reservation.qty,
                reserved_count: reservation.reserved_total ?? entry.reserved_count ?? 0,
                remaining: reservation.remaining ?? entry.remaining,
              }
            : entry,
        ),
      )
      setActionMessage('예약구매가 완료되었습니다.')
    } catch (error) {
      const message = error instanceof Error ? error.message : '예약구매 처리 중 오류가 발생했습니다.'
      setActionMessage(message)
    } finally {
      setProcessingId(null)
    }
  }

  return (
    <section className="preorders-page page-section">
      <div className="container">
        <header className="preorders-header">
          <h1 className="preorders-title">예약구매</h1>
          <p className="preorders-note">곧 출간되는 도서를 먼저 예약하고, 사전 혜택을 받아보세요.</p>
        </header>

        {actionMessage ? <div className="preorders-message">{actionMessage}</div> : null}

        {isLoading ? (
          <div className="preorder-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <article key={`preorder-skeleton-${index}`} className="preorder-card preorder-card--skeleton" />
            ))}
          </div>
        ) : errorMessage ? (
          <div className="event-panel-empty">{errorMessage}</div>
        ) : activeItems.length === 0 ? (
          <div className="event-panel-empty">현재 예약구매 가능한 도서가 없습니다.</div>
        ) : (
          <div className="preorder-grid">
            {activeItems.map((item) => {
              const isReserved = Boolean(item.reserved_by_me)
              const isProcessing = processingId === item.preorder_id
              const detailLink = `/book/${encodeURIComponent(item.doc_id)}?from=preorder`
              return (
                <article key={item.preorder_id} className="preorder-card">
                  <div className="preorder-cover-wrap">
                    <BookCover
                      className="preorder-cover"
                      title={item.title_ko}
                      docId={item.doc_id}
                      size="M"
                    />
                    <span className="preorder-badge">{item.badge ?? '출간 예정'}</span>
                  </div>
                  <div className="preorder-body">
                    <h2 className="preorder-book-title">{item.title_ko}</h2>
                    <p className="preorder-book-meta">{formatAuthors(item.authors)}</p>
                    <p className="preorder-book-meta">{item.publisher_name ?? '출판사 정보 없음'}</p>
                    <div className="preorder-price-row">
                      <strong className="preorder-price">{item.preorder_price_label ?? '-'}</strong>
                      {item.discount_rate ? <span className="preorder-discount">사전혜택 {item.discount_rate}%</span> : null}
                    </div>
                    <div className="preorder-window">
                      예약 마감 {formatDateLabel(item.preorder_end_at)} · 출간 {formatDateLabel(item.release_at)}
                    </div>
                    <div className="preorder-remaining">
                      {typeof item.remaining === 'number'
                        ? `남은 예약 수량 ${item.remaining}건`
                        : '예약 수량 제한 없음'}
                    </div>
                    <div className="preorder-actions">
                      <Link to={detailLink} className="btn btn-outline-dark btn-sm">
                        상세보기
                      </Link>
                      <button
                        type="button"
                        className={`btn btn-sm ${isReserved ? 'btn-outline-secondary' : 'btn-primary'}`}
                        onClick={() => handleReserve(item)}
                        disabled={isProcessing}
                      >
                        {isProcessing ? '처리 중...' : isReserved ? '예약수량 갱신' : (item.cta_label ?? '예약구매')}
                      </button>
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

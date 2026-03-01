import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getGiftItemById } from '../../services/myService'
import type { MyGiftItem } from '../../types/my'
import { formatWon } from './myPageUtils'

function resolveDirectionLabel(direction: MyGiftItem['direction']) {
  return direction === 'SENT' ? '보낸 선물' : '받은 선물'
}

export default function MyGiftDetailPage() {
  const { giftId } = useParams<{ giftId: string }>()
  const [item, setItem] = useState<MyGiftItem | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const targetId = giftId ?? ''
    getGiftItemById(targetId)
      .then((data) => {
        if (!active) return
        setItem(data)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [giftId])

  const totalPrice = useMemo(() => {
    if (!item) return 0
    return item.items.reduce((acc, book) => acc + book.unitPrice * book.quantity, 0)
  }, [item])

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>선물 상세</h1>
        <p>선물 상태와 도서 정보를 확인할 수 있습니다.</p>
      </header>

      <div className="my-panel">
        {loading ? <div className="my-muted">선물 정보를 불러오는 중입니다...</div> : null}

        {!loading && !item ? (
          <div className="my-empty">
            존재하지 않는 선물 내역입니다.
            <div className="mt-3">
              <Link to="/my/gifts" className="btn btn-sm btn-outline-secondary">
                선물함으로 돌아가기
              </Link>
            </div>
          </div>
        ) : null}

        {!loading && item ? (
          <div className="my-form-grid">
            <div className="my-panel-header">
              <h2 className="my-subtitle">{item.title}</h2>
              <span className="my-badge is-active">{item.status}</span>
            </div>

            <div className="my-list-table">
              <div className="my-list-row">
                <div>
                  <div className="my-list-title">구분</div>
                </div>
                <div className="my-list-meta">{resolveDirectionLabel(item.direction)}</div>
                <div className="my-list-meta" />
              </div>
              <div className="my-list-row">
                <div>
                  <div className="my-list-title">상대</div>
                </div>
                <div className="my-list-meta">{item.partnerName}</div>
                <div className="my-list-meta" />
              </div>
              <div className="my-list-row">
                <div>
                  <div className="my-list-title">선물일</div>
                </div>
                <div className="my-list-meta">{new Date(item.createdAt).toLocaleString('ko-KR')}</div>
                <div className="my-list-meta" />
              </div>
              {item.giftCode ? (
                <div className="my-list-row">
                  <div>
                    <div className="my-list-title">선물 코드</div>
                  </div>
                  <div className="my-list-meta">{item.giftCode}</div>
                  <div className="my-list-meta" />
                </div>
              ) : null}
              {item.expiresAt ? (
                <div className="my-list-row">
                  <div>
                    <div className="my-list-title">사용 만료일</div>
                  </div>
                  <div className="my-list-meta">{new Date(item.expiresAt).toLocaleString('ko-KR')}</div>
                  <div className="my-list-meta" />
                </div>
              ) : null}
            </div>

            <div>
              <h3 className="my-subtitle">선물 메시지</h3>
              <div className="my-muted">{item.message}</div>
            </div>

            <div>
              <h3 className="my-subtitle">도서 목록</h3>
              <div className="my-list-table">
                {item.items.map((book) => (
                  <div key={`${item.id}-${book.docId}`} className="my-list-row">
                    <div>
                      <div className="my-list-title">{book.title}</div>
                      <div className="my-list-sub">
                        {book.author} · {book.publisher}
                      </div>
                    </div>
                    <div className="my-list-meta">수량 {book.quantity}권</div>
                    <div className="my-list-meta">{formatWon(book.unitPrice * book.quantity)}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="my-panel-header">
              <strong>합계 {formatWon(totalPrice)}</strong>
              <Link to="/my/gifts" className="btn btn-sm btn-outline-secondary">
                목록으로
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

import { useEffect, useMemo, useState } from 'react'

import { listOrders, type OrderSummary } from '../../api/orders'
import { addComment, listComments } from '../../services/myService'
import type { MyComment } from '../../types/my'
import { formatDateTime, translateOrderStatus } from './myPageUtils'

const REVIEW_ALLOWED_STATUS = ['DELIVERED', 'PURCHASE_CONFIRMED', 'COMPLETED']

export default function MyCommentsPage() {
  const [orders, setOrders] = useState<OrderSummary[]>([])
  const [comments, setComments] = useState<MyComment[]>([])
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null)
  const [rating, setRating] = useState(5)
  const [content, setContent] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    Promise.all([listOrders(100), listComments()]).then(([orderItems, commentItems]) => {
      if (!active) return
      setOrders(orderItems)
      setComments(commentItems)
      const firstEligible = orderItems.find((order) => REVIEW_ALLOWED_STATUS.includes(order.status.toUpperCase()))
      setSelectedOrderId(firstEligible?.order_id ?? null)
    })

    return () => {
      active = false
    }
  }, [])

  const eligibleOrders = useMemo(
    () => orders.filter((order) => REVIEW_ALLOWED_STATUS.includes(order.status.toUpperCase())),
    [orders],
  )

  const selectedOrder = useMemo(
    () => eligibleOrders.find((order) => order.order_id === selectedOrderId) ?? null,
    [eligibleOrders, selectedOrderId],
  )

  const handleSubmit = async () => {
    if (!selectedOrder || !content.trim()) {
      setNotice('구매 확정된 주문과 코멘트 내용을 확인해 주세요.')
      return
    }

    const next = await addComment({
      orderId: selectedOrder.order_id,
      title: selectedOrder.primary_item_title ?? `주문 #${selectedOrder.order_id}`,
      rating,
      content: content.trim(),
    })

    setComments((prev) => [next, ...prev])
    setContent('')
    setNotice('코멘트가 등록되었습니다.')
  }

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>코멘트</h1>
        <p>배송 완료(구매 확정)된 주문에 한해서만 코멘트를 작성할 수 있습니다.</p>
      </header>

      <section className="my-panel">
        <h2 className="my-subtitle">리뷰 작성 가능 주문</h2>
        {eligibleOrders.length === 0 ? (
          <div className="my-empty">아직 코멘트를 작성할 수 있는 주문이 없습니다.</div>
        ) : (
          <div className="my-chip-row">
            {eligibleOrders.map((order) => (
              <button
                key={order.order_id}
                type="button"
                className={`my-chip ${selectedOrderId === order.order_id ? 'is-active' : ''}`}
                onClick={() => setSelectedOrderId(order.order_id)}
              >
                {order.primary_item_title ?? `주문 #${order.order_id}`}
              </button>
            ))}
          </div>
        )}

        <div className="my-form-grid mt-3">
          <label>
            평점
            <select value={rating} onChange={(event) => setRating(Number(event.target.value))}>
              {[5, 4, 3, 2, 1].map((score) => (
                <option key={score} value={score}>
                  {score}점
                </option>
              ))}
            </select>
          </label>
          <label>
            코멘트
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="도서와 배송 경험을 작성해 주세요."
              rows={4}
            />
          </label>
          <button type="button" className="btn btn-primary align-self-start" onClick={handleSubmit}>
            코멘트 등록
          </button>
        </div>

        {selectedOrder ? (
          <div className="my-muted mt-2">
            선택 주문 상태: {translateOrderStatus(selectedOrder.status)} / 주문번호 {selectedOrder.order_no ?? selectedOrder.order_id}
          </div>
        ) : null}
        {notice ? <div className="my-notice mt-2">{notice}</div> : null}
      </section>

      <section className="my-panel mt-4">
        <h2 className="my-subtitle">작성한 코멘트</h2>
        {comments.length === 0 ? <div className="my-empty">작성한 코멘트가 없습니다.</div> : null}

        {comments.length > 0 ? (
          <div className="my-comment-list">
            {comments.map((comment) => (
              <article key={comment.id} className="my-comment-card">
                <header>
                  <strong>{comment.title}</strong>
                  <span>{comment.rating}점</span>
                </header>
                <p>{comment.content}</p>
                <small>{formatDateTime(comment.createdAt)}</small>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </section>
  )
}

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listOrders, type OrderSummary } from '../../api/orders'

const ORDER_STATUS_LABEL: Record<string, string> = {
  CREATED: '주문 생성',
  PAYMENT_PENDING: '결제 대기',
  PAID: '결제 완료',
  READY_TO_SHIP: '배송 준비',
  SHIPPED: '배송 중',
  DELIVERED: '배송 완료',
  CANCELED: '주문 취소',
  REFUND_PENDING: '환불 처리 중',
  PARTIALLY_REFUNDED: '부분 환불',
  REFUNDED: '환불 완료',
}

function statusLabel(status: string) {
  return ORDER_STATUS_LABEL[status] ?? status
}

function shippingLabel(mode?: string) {
  return mode === 'FAST' ? '빠른배송' : '기본배송'
}

function itemSummary(order: OrderSummary) {
  const title = order.primary_item_title?.trim()
  const itemCount = order.item_count ?? 0
  if (title) {
    if (itemCount > 1) {
      return `${title} 외 ${itemCount - 1}권`
    }
    return title
  }
  return `주문 상품 ${itemCount > 0 ? `${itemCount}권` : '정보 없음'}`
}

export default function OrderListPage() {
  const [orders, setOrders] = useState<OrderSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    listOrders(20)
      .then((items) => {
        if (!active) return
        setOrders(items)
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : '주문 내역을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  if (loading) {
    return (
      <div className="container py-5">
        <div className="card p-4">주문 내역을 불러오는 중입니다...</div>
      </div>
    )
  }

  if (errorMessage) {
    return (
      <div className="container py-5">
        <div className="alert alert-danger">{errorMessage}</div>
      </div>
    )
  }

  if (orders.length === 0) {
    return (
      <div className="container py-5">
        <div className="order-empty text-center p-5">
          <h2 className="mb-3">주문 내역이 없습니다</h2>
          <p className="text-muted mb-4">도서를 주문하면 이곳에서 배송 상태를 확인할 수 있습니다.</p>
          <Link to="/search" className="btn btn-primary">
            도서 둘러보기
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      <h2 className="mb-4">주문 내역</h2>
      <div className="d-flex flex-column gap-3">
        {orders.map((order) => (
          <Link to={`/orders/${order.order_id}`} key={order.order_id} className="card order-card p-3">
            <div className="d-flex justify-content-between align-items-start">
              <div className="d-flex flex-column gap-1">
                <div className="text-muted small">주문번호 {order.order_no ?? order.order_id}</div>
                <div className="fw-semibold">{itemSummary(order)}</div>
                <div className="text-muted small">
                  {order.primary_item_author ? `${order.primary_item_author} · ` : ''}
                  {shippingLabel(order.shipping_mode)} · {statusLabel(order.status)}
                </div>
                <div className="text-muted small">
                  주문일 {new Date(order.created_at).toLocaleDateString('ko-KR')}
                </div>
              </div>
              <div className="fw-semibold">{order.total_amount.toLocaleString()}원</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

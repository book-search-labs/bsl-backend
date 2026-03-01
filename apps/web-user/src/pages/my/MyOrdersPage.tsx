import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { listOrders, type OrderSummary } from '../../api/orders'
import { formatWon, translateOrderStatus } from './myPageUtils'

function countByStatus(orders: OrderSummary[], statuses: string[]) {
  const targets = statuses.map((status) => status.toUpperCase())
  return orders.filter((order) => targets.includes(order.status.toUpperCase())).length
}

export default function MyOrdersPage() {
  const [orders, setOrders] = useState<OrderSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    listOrders(100)
      .then((items) => {
        if (!active) return
        setOrders(items)
        setError(null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : '주문 내역을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  const summary = useMemo(
    () => [
      { label: '결제 대기', count: countByStatus(orders, ['CREATED', 'PAYMENT_PENDING']) },
      { label: '배송 준비', count: countByStatus(orders, ['PAID', 'READY_TO_SHIP']) },
      { label: '배송 중', count: countByStatus(orders, ['SHIPPED']) },
      { label: '배송 완료', count: countByStatus(orders, ['DELIVERED']) },
      { label: '취소/환불', count: countByStatus(orders, ['CANCELLED', 'REFUND_PENDING', 'REFUNDED']) },
    ],
    [orders],
  )

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>주문/배송 목록</h1>
        <p>주문 상태와 결제 금액을 실시간으로 확인할 수 있습니다.</p>
      </header>

      <div className="my-status-grid">
        {summary.map((item) => (
          <article key={item.label} className="my-status-card">
            <div className="my-status-count">{item.count}</div>
            <div className="my-status-label">{item.label}</div>
          </article>
        ))}
      </div>

      <section className="my-panel mt-4">
        {loading ? <div className="my-muted">주문 내역을 불러오는 중입니다...</div> : null}
        {error ? <div className="alert alert-danger">{error}</div> : null}

        {!loading && !error && orders.length === 0 ? (
          <div className="my-empty">최근 주문 내역이 없습니다.</div>
        ) : null}

        {!loading && !error && orders.length > 0 ? (
          <div className="my-list-table">
            {orders.map((order) => (
              <Link to={`/orders/${order.order_id}`} key={order.order_id} className="my-list-row">
                <div>
                  <div className="my-list-title">{order.primary_item_title ?? `주문 #${order.order_id}`}</div>
                  <div className="my-list-sub">주문번호 {order.order_no ?? order.order_id}</div>
                </div>
                <div className="my-list-meta">{translateOrderStatus(order.status)}</div>
                <div className="my-list-meta">{formatWon(order.total_amount)}</div>
              </Link>
            ))}
          </div>
        ) : null}
      </section>
    </section>
  )
}

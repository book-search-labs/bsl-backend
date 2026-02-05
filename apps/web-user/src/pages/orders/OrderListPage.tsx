import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listOrders, type OrderSummary } from '../../api/orders'

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
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load orders')
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
        <div className="card p-4">Loading orders...</div>
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
          <h2 className="mb-3">No orders yet</h2>
          <p className="text-muted mb-4">When you place an order, it will appear here.</p>
          <Link to="/search" className="btn btn-primary">
            Start shopping
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      <h2 className="mb-4">Order History</h2>
      <div className="d-flex flex-column gap-3">
        {orders.map((order) => (
          <Link to={`/orders/${order.order_id}`} key={order.order_id} className="card order-card p-3">
            <div className="d-flex justify-content-between align-items-start">
              <div>
                <div className="text-muted small">Order #{order.order_no ?? order.order_id}</div>
                <div className="fw-semibold">Status: {order.status}</div>
                <div className="text-muted small">Placed {new Date(order.created_at).toLocaleDateString()}</div>
              </div>
              <div className="fw-semibold">₩{order.total_amount.toLocaleString()}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

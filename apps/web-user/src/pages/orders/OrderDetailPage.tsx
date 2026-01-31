import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getOrder, cancelOrder } from '../../api/orders'
import { getShipmentsByOrder } from '../../api/shipments'

export default function OrderDetailPage() {
  const { orderId } = useParams()
  const [orderDetail, setOrderDetail] = useState<Awaited<ReturnType<typeof getOrder>> | null>(null)
  const [shipments, setShipments] = useState<Awaited<ReturnType<typeof getShipmentsByOrder>>>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!orderId) return
    let active = true
    getOrder(Number(orderId))
      .then((data) => {
        if (!active) return
        setOrderDetail(data)
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load order')
      })

    getShipmentsByOrder(Number(orderId))
      .then((items) => {
        if (!active) return
        setShipments(items)
      })
      .catch(() => {
        // ignore shipment errors
      })

    return () => {
      active = false
    }
  }, [orderId])

  const order = orderDetail?.order
  const canCancel = order?.status === 'PAYMENT_PENDING' || order?.status === 'CREATED'
  const canRefund = order && ['PAID', 'SHIPPED', 'DELIVERED'].includes(order.status)

  const statusTimeline = useMemo(() => {
    const events = orderDetail?.events ?? []
    const ordered = ['CREATED', 'PAYMENT_PENDING', 'PAID', 'READY_TO_SHIP', 'SHIPPED', 'DELIVERED']
    const map: Record<string, string | null> = {}
    events.forEach((event) => {
      if (event.to_status) {
        map[event.to_status] = event.created_at ?? null
      }
    })
    return ordered.map((status) => ({ status, timestamp: map[status] }))
  }, [orderDetail])

  const handleCancel = async () => {
    if (!orderId) return
    try {
      const data = await cancelOrder(Number(orderId), 'user_requested')
      setOrderDetail(data)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to cancel order')
    }
  }

  if (errorMessage) {
    return (
      <div className="container py-5">
        <div className="alert alert-danger">{errorMessage}</div>
      </div>
    )
  }

  if (!orderDetail) {
    return (
      <div className="container py-5">
        <div className="card p-4">Loading order...</div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      <div className="order-detail card p-4 mb-4">
        <div className="d-flex justify-content-between align-items-start">
          <div>
            <h2>Order #{order?.order_no ?? order?.order_id}</h2>
            <p className="text-muted">Status: {order?.status}</p>
          </div>
          <div className="fw-semibold fs-4">₩{order ? order.total_amount.toLocaleString() : '0'}</div>
        </div>
        <div className="d-flex gap-2 mt-3">
          {canCancel ? (
            <button className="btn btn-outline-danger" onClick={handleCancel}>
              Cancel order
            </button>
          ) : null}
          {canRefund ? (
            <Link to={`/orders/${order?.order_id}/refund`} className="btn btn-outline-secondary">
              Request refund
            </Link>
          ) : null}
        </div>
      </div>

      <div className="row g-4">
        <div className="col-lg-7">
          <div className="card p-4 mb-4">
            <h4 className="mb-3">Items</h4>
            <div className="d-flex flex-column gap-2">
              {orderDetail.items.map((item) => (
                <div key={item.order_item_id} className="d-flex justify-content-between">
                  <div>
                    <div className="fw-semibold">SKU #{item.sku_id}</div>
                    <div className="text-muted small">Qty {item.qty}</div>
                  </div>
                  <div>₩{item.item_amount.toLocaleString()}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h4 className="mb-3">Shipment</h4>
            {shipments.length === 0 ? (
              <div className="text-muted">No shipment yet.</div>
            ) : (
              shipments.map((shipment) => (
                <div key={shipment.shipment_id} className="shipment-card mb-3">
                  <div className="fw-semibold">Status: {shipment.status}</div>
                  <div className="text-muted small">
                    {shipment.carrier ? `${shipment.carrier} ${shipment.tracking_no ?? ''}` : 'Tracking pending'}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="col-lg-5">
          <div className="card p-4">
            <h4 className="mb-3">Order Timeline</h4>
            <div className="timeline">
              {statusTimeline.map((step) => (
                <div key={step.status} className="timeline-step">
                  <div className="timeline-dot" />
                  <div>
                    <div className="fw-semibold">{step.status}</div>
                    <div className="text-muted small">
                      {step.timestamp ? new Date(step.timestamp).toLocaleString() : 'Pending'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

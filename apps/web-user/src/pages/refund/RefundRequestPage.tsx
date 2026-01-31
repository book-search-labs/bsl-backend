import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { createRefund } from '../../api/refund'
import { getOrder } from '../../api/orders'

export default function RefundRequestPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [orderDetail, setOrderDetail] = useState<Awaited<ReturnType<typeof getOrder>> | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [reason, setReason] = useState('CHANGE_OF_MIND')
  const [detailReason, setDetailReason] = useState('')
  const [selectedQty, setSelectedQty] = useState<Record<number, number>>({})

  useEffect(() => {
    if (!orderId) return
    let active = true
    getOrder(Number(orderId))
      .then((data) => {
        if (!active) return
        setOrderDetail(data)
        const initial: Record<number, number> = {}
        data.items.forEach((item) => {
          initial[item.order_item_id] = item.qty
        })
        setSelectedQty(initial)
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load order')
      })
    return () => {
      active = false
    }
  }, [orderId])

  const items = orderDetail?.items ?? []
  const hasSelection = useMemo(() => Object.values(selectedQty).some((qty) => qty > 0), [selectedQty])

  const handleSubmit = async () => {
    if (!orderId) return
    if (!hasSelection) {
      setErrorMessage('Select at least one item to refund')
      return
    }
    try {
      const payload = {
        orderId: Number(orderId),
        reasonCode: reason,
        reasonText: detailReason,
        items: items
          .filter((item) => selectedQty[item.order_item_id] > 0)
          .map((item) => ({ orderItemId: item.order_item_id, qty: selectedQty[item.order_item_id] })),
      }
      await createRefund(payload)
      navigate(`/orders/${orderId}`)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to request refund')
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
      <div className="card p-4">
        <h2 className="mb-3">Request Refund</h2>
        {errorMessage ? <div className="alert alert-danger">{errorMessage}</div> : null}
        <div className="mb-4">
          <label className="form-label">Reason</label>
          <select className="form-select" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="CHANGE_OF_MIND">Change of mind</option>
            <option value="DAMAGED">Damaged product</option>
            <option value="LATE_DELIVERY">Late delivery</option>
            <option value="OTHER">Other</option>
          </select>
          <textarea
            className="form-control mt-2"
            placeholder="Additional details (optional)"
            rows={3}
            value={detailReason}
            onChange={(e) => setDetailReason(e.target.value)}
          />
        </div>

        <div className="refund-items">
          <h5>Items</h5>
          {items.map((item) => (
            <div key={item.order_item_id} className="d-flex justify-content-between align-items-center border-bottom py-2">
              <div>
                <div className="fw-semibold">SKU #{item.sku_id}</div>
                <div className="text-muted small">Ordered qty: {item.qty}</div>
              </div>
              <input
                type="number"
                className="form-control form-control-sm"
                style={{ width: 80 }}
                min={0}
                max={item.qty}
                value={selectedQty[item.order_item_id] ?? 0}
                onChange={(e) =>
                  setSelectedQty({
                    ...selectedQty,
                    [item.order_item_id]: Math.min(item.qty, Math.max(0, Number(e.target.value))),
                  })
                }
              />
            </div>
          ))}
        </div>

        <div className="mt-4 d-flex gap-2">
          <button className="btn btn-primary" onClick={handleSubmit}>
            Submit refund request
          </button>
          <button className="btn btn-outline-secondary" onClick={() => navigate(-1)}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

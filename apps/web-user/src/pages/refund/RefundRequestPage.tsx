import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { createRefund } from '../../api/refund'
import { getOrder } from '../../api/orders'

const SELLER_FAULT_REASONS = new Set(['DAMAGED', 'DEFECTIVE', 'WRONG_ITEM', 'LATE_DELIVERY'])

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
        setErrorMessage(err instanceof Error ? err.message : '주문 정보를 불러오지 못했습니다.')
      })
    return () => {
      active = false
    }
  }, [orderId])

  const items = orderDetail?.items ?? []
  const hasSelection = useMemo(() => Object.values(selectedQty).some((qty) => qty > 0), [selectedQty])
  const selectedItemAmount = useMemo(
    () => items.reduce((sum, item) => sum + (selectedQty[item.order_item_id] ?? 0) * item.unit_price, 0),
    [items, selectedQty],
  )
  const selectedItemQty = useMemo(
    () => items.reduce((sum, item) => sum + (selectedQty[item.order_item_id] ?? 0), 0),
    [items, selectedQty],
  )
  const selectedAllItems = useMemo(
    () => items.length > 0 && items.every((item) => (selectedQty[item.order_item_id] ?? 0) >= item.qty),
    [items, selectedQty],
  )
  const estimatedPricing = useMemo(() => {
    const status = orderDetail?.order.status
    const shippingFee = orderDetail?.order.shipping_fee ?? 0
    const shippingMode = orderDetail?.order.shipping_mode

    let shippingRefund = 0
    let returnFee = 0

    if (status === 'PAID' || status === 'READY_TO_SHIP') {
      if (selectedAllItems) {
        shippingRefund = shippingFee
      }
    } else if (status === 'SHIPPED' || status === 'DELIVERED' || status === 'PARTIALLY_REFUNDED') {
      if (SELLER_FAULT_REASONS.has(reason)) {
        if (selectedAllItems) {
          shippingRefund = shippingFee
        }
      } else {
        returnFee = shippingMode === 'FAST' ? 5000 : 3000
      }
    }

    const gross = selectedItemAmount + shippingRefund
    const appliedReturnFee = Math.min(returnFee, gross)
    const net = Math.max(0, gross - appliedReturnFee)
    return {
      selectedItemAmount,
      shippingRefund,
      returnFee: appliedReturnFee,
      net,
    }
  }, [orderDetail, reason, selectedAllItems, selectedItemAmount])

  const handleSubmit = async () => {
    if (!orderId) return
    if (!hasSelection) {
      setErrorMessage('환불할 도서를 최소 1권 이상 선택해주세요.')
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
      setErrorMessage(err instanceof Error ? err.message : '환불 신청에 실패했습니다.')
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
        <div className="card p-4">주문 정보를 불러오는 중입니다...</div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      <div className="card p-4">
        <h2 className="mb-3">환불 신청</h2>
        {errorMessage ? <div className="alert alert-danger">{errorMessage}</div> : null}
        <div className="mb-4">
          <label className="form-label">환불 사유</label>
          <select className="form-select" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="CHANGE_OF_MIND">단순 변심</option>
            <option value="DAMAGED">상품 파손</option>
            <option value="DEFECTIVE">상품 하자</option>
            <option value="WRONG_ITEM">오배송</option>
            <option value="LATE_DELIVERY">배송 지연</option>
            <option value="OTHER">기타</option>
          </select>
          <textarea
            className="form-control mt-2"
            placeholder="상세 사유를 입력해주세요 (선택)"
            rows={3}
            value={detailReason}
            onChange={(e) => setDetailReason(e.target.value)}
          />
        </div>

        <div className="card mb-4">
          <div className="card-body py-3">
            <div className="d-flex justify-content-between small">
              <span>선택 상품 ({selectedItemQty}권)</span>
              <span>{estimatedPricing.selectedItemAmount.toLocaleString()}원</span>
            </div>
            <div className="d-flex justify-content-between small">
              <span>배송비 환불</span>
              <span>+{estimatedPricing.shippingRefund.toLocaleString()}원</span>
            </div>
            <div className="d-flex justify-content-between small">
              <span>반품 수수료</span>
              <span>-{estimatedPricing.returnFee.toLocaleString()}원</span>
            </div>
            <hr className="my-2" />
            <div className="d-flex justify-content-between fw-semibold">
              <span>예상 환불 금액</span>
              <span>{estimatedPricing.net.toLocaleString()}원</span>
            </div>
            <div className="text-muted small mt-2">최종 환불 금액은 주문 상태와 기존 환불 이력 기준으로 백엔드에서 확정됩니다.</div>
          </div>
        </div>

        <div className="refund-items">
          <h5>환불 대상 도서</h5>
          {items.map((item) => (
            <div key={item.order_item_id} className="d-flex justify-content-between align-items-center border-bottom py-2">
              <div>
                <div className="fw-semibold">{item.title ?? `도서 SKU #${item.sku_id}`}</div>
                <div className="text-muted small">
                  {[item.author, item.publisher].filter(Boolean).join(' · ') || '도서 정보 준비 중'}
                </div>
                <div className="text-muted small">주문 수량: {item.qty}권</div>
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
            환불 신청하기
          </button>
          <button className="btn btn-outline-secondary" onClick={() => navigate(-1)}>
            취소
          </button>
        </div>
      </div>
    </div>
  )
}

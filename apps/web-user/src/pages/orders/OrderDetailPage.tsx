import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { cancelOrder, getOrder } from '../../api/orders'
import BookCover from '../../components/books/BookCover'
import { getShipmentsByOrder } from '../../api/shipments'

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

const PAYMENT_LABEL: Record<string, string> = {
  CARD: '카드',
  TRANSFER: '계좌이체',
  EASY_PAY: '간편결제',
}

const SHIPMENT_STATUS_LABEL: Record<string, string> = {
  PENDING: '출고 대기',
  READY: '출고 준비',
  SHIPPED: '배송 중',
  DELIVERED: '배송 완료',
  RETURNED: '반품 완료',
  CANCELED: '배송 취소',
}

const ORDER_FLOW = ['CREATED', 'PAYMENT_PENDING', 'PAID', 'READY_TO_SHIP', 'SHIPPED', 'DELIVERED'] as const
const TERMINAL_STATUSES = ['CANCELED', 'REFUND_PENDING', 'PARTIALLY_REFUNDED', 'REFUNDED'] as const

const ORDER_STATUS_DESCRIPTION: Record<string, string> = {
  CREATED: '주문이 생성되었습니다.',
  PAYMENT_PENDING: '결제 대기 상태입니다. 결제가 완료되면 출고 준비로 이동합니다.',
  PAID: '결제가 확인되었습니다.',
  READY_TO_SHIP: '출고 준비 중입니다.',
  SHIPPED: '상품이 배송 중입니다.',
  DELIVERED: '배송이 완료되었습니다.',
  CANCELED: '주문이 취소되었습니다.',
  REFUND_PENDING: '환불 요청이 접수되어 검토 중입니다.',
  PARTIALLY_REFUNDED: '일부 금액이 환불되었습니다.',
  REFUNDED: '환불이 완료되었습니다.',
}

function statusLabel(status?: string | null) {
  if (!status) return '상태 정보 없음'
  return ORDER_STATUS_LABEL[status] ?? status
}

function paymentMethodLabel(method?: string | null) {
  if (!method) return '미정'
  return PAYMENT_LABEL[method] ?? method
}

function shippingModeLabel(mode?: string | null) {
  return mode === 'FAST' ? '빠른배송' : '기본배송'
}

function shipmentStatusLabel(status?: string | null) {
  if (!status) return '출고 대기'
  return SHIPMENT_STATUS_LABEL[status] ?? status
}

function formatDateTime(value?: string | null) {
  if (!value) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('ko-KR')
}

function timelineStateLabel(state: 'done' | 'current' | 'pending') {
  if (state === 'done') return '완료'
  if (state === 'current') return '현재'
  return '대기'
}

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
        setErrorMessage(err instanceof Error ? err.message : '주문 정보를 불러오지 못했습니다.')
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
  const canRefund = order && ['PAID', 'READY_TO_SHIP', 'SHIPPED', 'DELIVERED', 'PARTIALLY_REFUNDED'].includes(order.status)

  const statusTimeline = useMemo(() => {
    const events = orderDetail?.events ?? []
    const currentStatus = order?.status
    const isTerminalCurrent =
      !!currentStatus && TERMINAL_STATUSES.includes(currentStatus as (typeof TERMINAL_STATUSES)[number])

    const eventMap: Record<string, string | null> = {}
    events.forEach((event) => {
      if (event.to_status) {
        eventMap[event.to_status] = eventMap[event.to_status] ?? event.created_at ?? null
      }
    })

    if (!eventMap.CREATED) {
      eventMap.CREATED = order?.created_at ?? null
    }

    let maxReachedFlowIndex = -1
    ORDER_FLOW.forEach((status, idx) => {
      if (eventMap[status]) {
        maxReachedFlowIndex = Math.max(maxReachedFlowIndex, idx)
      }
    })

    if (currentStatus && ORDER_FLOW.includes(currentStatus as (typeof ORDER_FLOW)[number])) {
      maxReachedFlowIndex = Math.max(
        maxReachedFlowIndex,
        ORDER_FLOW.indexOf(currentStatus as (typeof ORDER_FLOW)[number]),
      )
    }

    if (isTerminalCurrent) {
      const terminalEvent = [...events].reverse().find((event) => event.to_status === currentStatus)
      const terminalFrom = terminalEvent?.from_status
      if (terminalFrom && ORDER_FLOW.includes(terminalFrom as (typeof ORDER_FLOW)[number])) {
        maxReachedFlowIndex = Math.max(
          maxReachedFlowIndex,
          ORDER_FLOW.indexOf(terminalFrom as (typeof ORDER_FLOW)[number]),
        )
      }
    }

    if (maxReachedFlowIndex < 0) {
      maxReachedFlowIndex = 0
    }

    const ordered: string[] = isTerminalCurrent
      ? [...ORDER_FLOW.slice(0, maxReachedFlowIndex + 1), currentStatus as string]
      : [...ORDER_FLOW]

    const currentIndex = currentStatus ? ordered.indexOf(currentStatus) : -1

    return ordered.map((status, idx) => {
      const timestamp = eventMap[status] ?? null
      let state: 'done' | 'current' | 'pending' = 'pending'

      if (currentStatus === status) {
        state = 'current'
      } else if (timestamp) {
        state = 'done'
      } else if (!isTerminalCurrent && currentIndex >= 0 && idx < currentIndex) {
        state = 'done'
      }

      return {
        status,
        timestamp,
        state,
        description: ORDER_STATUS_DESCRIPTION[status] ?? '주문 상태를 확인 중입니다.',
      }
    })
  }, [orderDetail, order?.status])

  const currentStep = statusTimeline.find((step) => step.state === 'current')
  const nextStep = statusTimeline.find((step) => step.state === 'pending')

  const handleCancel = async () => {
    if (!orderId) return
    try {
      const data = await cancelOrder(Number(orderId), 'user_requested')
      setOrderDetail(data)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '주문 취소에 실패했습니다.')
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
      <div className="order-detail card p-4 mb-4">
        <div className="d-flex justify-content-between align-items-start gap-3">
          <div>
            <h2 className="mb-1">주문번호 {order?.order_no ?? order?.order_id}</h2>
            <p className="text-muted mb-1">주문 상태: {statusLabel(order?.status)}</p>
            <p className="text-muted mb-0">
              {shippingModeLabel(order?.shipping_mode)} · {paymentMethodLabel(order?.payment_method)} ·{' '}
              {formatDateTime(order?.created_at) ?? '-'}
            </p>
            <p className="text-muted small mb-0 mt-1">
              {ORDER_STATUS_DESCRIPTION[order?.status ?? ''] ?? '현재 주문 상태를 확인해 주세요.'}
            </p>
          </div>
          <div className="fw-semibold fs-4">{order ? `${order.total_amount.toLocaleString()}원` : '0원'}</div>
        </div>
        <div className="d-flex gap-2 mt-3">
          {canCancel ? (
            <button className="btn btn-outline-danger" onClick={handleCancel}>
              주문 취소
            </button>
          ) : null}
          {canRefund ? (
            <Link to={`/orders/${order?.order_id}/refund`} className="btn btn-outline-secondary">
              환불 신청
            </Link>
          ) : null}
        </div>
      </div>

      <div className="row g-4">
        <div className="col-lg-7">
          <div className="card p-4 mb-4">
            <h4 className="mb-3">주문 도서</h4>
            <div className="d-flex flex-column gap-2">
              {orderDetail.items.map((item) => (
                <article key={item.order_item_id} className="order-detail-item">
                  <Link to={item.material_id ? `/book/${encodeURIComponent(item.material_id)}` : '/search'} className="order-item-cover">
                    <BookCover
                      className="book-cover-image"
                      title={item.title ?? '도서 표지'}
                      coverUrl={item.cover_url ?? null}
                      isbn13={item.isbn13 ?? null}
                      docId={item.material_id ?? `sku:${item.sku_id}`}
                      size="M"
                    />
                  </Link>
                  <div className="order-item-body">
                    <div className="fw-semibold">{item.title ?? `도서 SKU #${item.sku_id}`}</div>
                    <div className="text-muted small">
                      {[item.author, item.publisher].filter(Boolean).join(' · ') || '도서 정보 준비 중'}
                    </div>
                    <div className="text-muted small">
                      {item.seller_name ? `${item.seller_name} · ` : ''}
                      수량 {item.qty}권
                    </div>
                  </div>
                  <div className="order-item-price">
                    <div className="fw-semibold">{item.item_amount.toLocaleString()}원</div>
                    <div className="text-muted small">{item.unit_price.toLocaleString()}원 / 권</div>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h4 className="mb-3">배송 정보</h4>
            {shipments.length === 0 ? (
              <div className="text-muted">아직 출고 정보가 없습니다.</div>
            ) : (
              shipments.map((shipment) => (
                <div key={shipment.shipment_id} className="shipment-card mb-3">
                  <div className="fw-semibold">상태: {shipmentStatusLabel(shipment.status)}</div>
                  <div className="text-muted small">
                    {shipment.carrier
                      ? `${shipment.carrier} ${shipment.tracking_no ?? ''}`.trim()
                      : '송장 정보 등록 대기'}
                  </div>
                  {shipment.shipped_at ? (
                    <div className="text-muted small">출고일: {formatDateTime(shipment.shipped_at)}</div>
                  ) : null}
                  {shipment.delivered_at ? (
                    <div className="text-muted small">배송완료일: {formatDateTime(shipment.delivered_at)}</div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="col-lg-5">
          <div className="card p-4">
            <h4 className="mb-3">주문 진행 내역</h4>
            <div className="timeline-summary mb-3">
              <div className="timeline-summary-row">
                <span className="text-muted small">현재 단계</span>
                <span className="fw-semibold">{currentStep ? statusLabel(currentStep.status) : statusLabel(order?.status)}</span>
              </div>
              <div className="timeline-summary-row">
                <span className="text-muted small">다음 단계</span>
                <span className="small">{nextStep ? statusLabel(nextStep.status) : '마지막 단계입니다.'}</span>
              </div>
            </div>
            <div className="timeline">
              {statusTimeline.map((step) => (
                <div key={step.status} className={`timeline-step ${step.state}`}>
                  <div className="timeline-dot" />
                  <div>
                    <div className="d-flex align-items-center gap-2">
                      <div className="fw-semibold">{statusLabel(step.status)}</div>
                      <span className={`timeline-state-chip ${step.state}`}>{timelineStateLabel(step.state)}</span>
                    </div>
                    <div className="text-muted small">
                      {step.timestamp ? formatDateTime(step.timestamp) : step.state === 'pending' ? '진행 전' : '처리 중'}
                    </div>
                    <div className="text-muted small">{step.description}</div>
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

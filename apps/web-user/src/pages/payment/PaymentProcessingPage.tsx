import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { createPayment, getPayment, mockCompletePayment, type Payment } from '../../api/payment'
import { getOrder } from '../../api/orders'

const TERMINAL_STATUSES = new Set(['CAPTURED', 'FAILED', 'CANCELED', 'REFUNDED'])

function resolvePaymentId(searchParams: URLSearchParams): number | null {
  const raw = searchParams.get('payment_id') ?? searchParams.get('paymentId')
  if (!raw) return null
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

export default function PaymentProcessingPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const returnedPaymentId = useMemo(() => resolvePaymentId(searchParams), [searchParams])

  const [paymentId, setPaymentId] = useState<number | null>(returnedPaymentId)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [status, setStatus] = useState<string>('INIT')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [pollAttempts, setPollAttempts] = useState(0)

  useEffect(() => {
    if (!orderId) return
    let active = true

    const beginCheckout = async () => {
      if (returnedPaymentId) {
        setPaymentId(returnedPaymentId)
        setStatus('PROCESSING')
        return
      }

      try {
        setStatus('LOADING')
        const orderResponse = await getOrder(Number(orderId))
        const order = orderResponse.order
        const returnUrl = `${window.location.origin}/payment/process/${order.order_id}`

        const created = await createPayment({
          orderId: order.order_id,
          amount: order.total_amount,
          method: order.payment_method ?? 'CARD',
          idempotencyKey: `pay_${order.order_id}`,
          provider: 'LOCAL_SIM',
          returnUrl,
        })
        if (!active) return

        setPaymentId(created.payment_id)
        setPayment(created)

        if (TERMINAL_STATUSES.has(created.status)) {
          navigate(`/payment/result/${created.payment_id}?status=${created.status}`, { replace: true })
          return
        }

        if (created.checkout_url) {
          setStatus('REDIRECTING')
          window.location.assign(created.checkout_url)
          return
        }

        setStatus('READY')
      } catch (err) {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : '결제 초기화에 실패했습니다.')
        setStatus('ERROR')
      }
    }

    beginCheckout()

    return () => {
      active = false
    }
  }, [navigate, orderId, returnedPaymentId])

  useEffect(() => {
    if (!paymentId) return
    if (!(status === 'PROCESSING' || status === 'REDIRECTING' || status === 'POLLING' || status === 'TIMEOUT')) {
      return
    }

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async (attempt: number) => {
      if (cancelled) return
      try {
        setStatus('POLLING')
        setPollAttempts(attempt)
        const latest = await getPayment(paymentId)
        if (cancelled) return
        setPayment(latest)

        if (TERMINAL_STATUSES.has(latest.status)) {
          navigate(`/payment/result/${latest.payment_id}?status=${latest.status}`, { replace: true })
          return
        }

        if (attempt >= 30) {
          setStatus('TIMEOUT')
          return
        }

        timer = setTimeout(() => poll(attempt + 1), 1000)
      } catch (err) {
        if (cancelled) return
        setErrorMessage(err instanceof Error ? err.message : '결제 상태 확인에 실패했습니다.')
        setStatus('ERROR')
      }
    }

    poll(1)

    return () => {
      cancelled = true
      if (timer) {
        clearTimeout(timer)
      }
    }
  }, [paymentId, status, navigate])

  const retryPolling = () => {
    if (!paymentId) return
    setErrorMessage(null)
    setStatus('PROCESSING')
    setPollAttempts(0)
  }

  const handleMockFallback = async (result: 'SUCCESS' | 'FAIL') => {
    if (!paymentId) return
    try {
      setStatus('PROCESSING')
      await mockCompletePayment(paymentId, result)
      setStatus('POLLING')
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '모의 결제 처리에 실패했습니다.')
      setStatus('ERROR')
    }
  }

  return (
    <div className="container py-5">
      <div className="payment-processing card p-4 shadow-sm">
        <h2 className="mb-3">결제 처리중</h2>
        <p className="text-muted">주문번호 {orderId}</p>
        {payment ? (
          <div className="text-muted small mb-3">
            결제번호 {payment.payment_id} · 상태 {payment.status}
          </div>
        ) : null}
        {errorMessage ? <div className="alert alert-danger">{errorMessage}</div> : null}

        {status === 'LOADING' ? <div className="text-muted">결제 세션을 준비하고 있습니다...</div> : null}
        {status === 'REDIRECTING' ? <div className="text-muted">결제창으로 이동 중입니다...</div> : null}
        {status === 'POLLING' ? (
          <div className="text-muted">결제 결과를 확인 중입니다... ({pollAttempts}/30)</div>
        ) : null}
        {status === 'TIMEOUT' ? (
          <div className="d-flex flex-column gap-2">
            <div className="alert alert-warning mb-0">결제 확정이 지연되고 있습니다. 상태 확인을 다시 시도해주세요.</div>
            <button className="btn btn-primary" onClick={retryPolling}>
              결제 상태 확인
            </button>
          </div>
        ) : null}

        {status === 'READY' ? (
          <div className="d-flex flex-column gap-3">
            <div className="alert alert-info mb-0">
              체크아웃 URL이 없어 개발용 fallback 모드로 전환되었습니다.
            </div>
            <div className="d-flex gap-2">
              <button className="btn btn-success" onClick={() => handleMockFallback('SUCCESS')}>
                결제 성공 처리
              </button>
              <button className="btn btn-outline-danger" onClick={() => handleMockFallback('FAIL')}>
                결제 실패 처리
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

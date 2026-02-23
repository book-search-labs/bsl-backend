import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { getPayment } from '../../api/payment'

const PAYMENT_STATUS_LABEL: Record<string, string> = {
  INITIATED: '결제 시작',
  AUTHORIZED: '승인 완료',
  CAPTURED: '결제 완료',
  FAILED: '결제 실패',
  CANCELED: '결제 취소',
  REFUNDED: '환불 완료',
}

function paymentStatusLabel(status: string) {
  return PAYMENT_STATUS_LABEL[status] ?? status
}

export default function PaymentResultPage() {
  const { paymentId } = useParams()
  const [searchParams] = useSearchParams()
  const [payment, setPayment] = useState<Awaited<ReturnType<typeof getPayment>> | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const status = searchParams.get('status')

  useEffect(() => {
    if (!paymentId) return
    let active = true
    getPayment(Number(paymentId))
      .then((data) => {
        if (!active) return
        setPayment(data)
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : '결제 정보를 불러오지 못했습니다.')
      })
    return () => {
      active = false
    }
  }, [paymentId])

  const normalizedStatus = payment?.status ?? status ?? 'UNKNOWN'
  const isSuccess = normalizedStatus === 'CAPTURED'

  return (
    <div className="container py-5">
      <div className={`card p-4 shadow-sm ${isSuccess ? 'border-success' : 'border-danger'}`}>
        <h2 className="mb-3">{isSuccess ? '결제가 완료되었습니다.' : '결제에 실패했습니다.'}</h2>
        {errorMessage ? <div className="alert alert-danger">{errorMessage}</div> : null}
        {payment ? (
          <div className="mb-3">
            <div className="text-muted">결제번호 {payment.payment_id}</div>
            <div className="fw-semibold">결제 금액 {payment.amount.toLocaleString()}원</div>
            <div className="text-muted">결제 상태: {paymentStatusLabel(payment.status)}</div>
          </div>
        ) : null}
        <div className="d-flex gap-2">
          <Link to="/orders" className="btn btn-primary">
            주문 내역 보기
          </Link>
          <Link to="/search" className="btn btn-outline-secondary">
            쇼핑 계속하기
          </Link>
        </div>
      </div>
    </div>
  )
}

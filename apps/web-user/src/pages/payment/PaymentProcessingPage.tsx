import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { createPayment, mockCompletePayment } from '../../api/payment'
import { getOrder } from '../../api/orders'

export default function PaymentProcessingPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [paymentId, setPaymentId] = useState<number | null>(null)
  const [status, setStatus] = useState<string>('INIT')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!orderId) return
    let active = true
    const run = async () => {
      try {
        setStatus('LOADING')
        const orderResponse = await getOrder(Number(orderId))
        const order = orderResponse.order
        const payment = await createPayment({
          orderId: order.order_id,
          amount: order.total_amount,
          method: order.payment_method ?? 'CARD',
          idempotencyKey: `pay_${order.order_id}`,
        })
        if (!active) return
        setPaymentId(payment.payment_id)
        setStatus('READY')
      } catch (err) {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : '결제 초기화에 실패했습니다.')
        setStatus('ERROR')
      }
    }
    run()
    return () => {
      active = false
    }
  }, [orderId])

  const handleComplete = async (result: 'SUCCESS' | 'FAIL') => {
    if (!paymentId) return
    try {
      setStatus('PROCESSING')
      const payment = await mockCompletePayment(paymentId, result)
      navigate(`/payment/result/${payment.payment_id}?status=${payment.status}`)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '결제 처리에 실패했습니다.')
      setStatus('ERROR')
    }
  }

  return (
    <div className="container py-5">
      <div className="payment-processing card p-4 shadow-sm">
        <h2 className="mb-3">결제 진행</h2>
        <p className="text-muted">주문번호 {orderId}</p>
        {errorMessage ? <div className="alert alert-danger">{errorMessage}</div> : null}
        {status === 'READY' ? (
          <div className="d-flex flex-column gap-3">
            <div className="alert alert-info">
              현재는 테스트 결제 모드입니다. 결제 결과를 선택해 진행해주세요.
            </div>
            <div className="d-flex gap-2">
              <button className="btn btn-success" onClick={() => handleComplete('SUCCESS')}>
                결제 성공 처리
              </button>
              <button className="btn btn-outline-danger" onClick={() => handleComplete('FAIL')}>
                결제 실패 처리
              </button>
            </div>
          </div>
        ) : null}
        {status === 'LOADING' ? <div className="mt-3 text-muted">결제 정보를 준비하고 있습니다...</div> : null}
        {status === 'PROCESSING' ? <div className="mt-3 text-muted">결제를 확정하는 중입니다...</div> : null}
      </div>
    </div>
  )
}

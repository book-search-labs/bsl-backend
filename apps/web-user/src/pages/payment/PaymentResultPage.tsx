import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { getPayment } from '../../api/payment'

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
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load payment')
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
        <h2 className="mb-3">{isSuccess ? 'Payment Successful' : 'Payment Failed'}</h2>
        {errorMessage ? <div className="alert alert-danger">{errorMessage}</div> : null}
        {payment ? (
          <div className="mb-3">
            <div className="text-muted">Payment #{payment.payment_id}</div>
            <div className="fw-semibold">Amount ₩{payment.amount.toLocaleString()}</div>
            <div className="text-muted">Status: {payment.status}</div>
          </div>
        ) : null}
        <div className="d-flex gap-2">
          <Link to="/orders" className="btn btn-primary">
            View orders
          </Link>
          <Link to="/search" className="btn btn-outline-secondary">
            Continue shopping
          </Link>
        </div>
      </div>
    </div>
  )
}

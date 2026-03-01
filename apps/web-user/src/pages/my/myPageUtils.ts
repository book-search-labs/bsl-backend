export function formatWon(value: number) {
  return `₩${new Intl.NumberFormat('ko-KR').format(value)}`
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

export function translateOrderStatus(status: string) {
  const normalized = status.toUpperCase()
  if (normalized === 'CREATED' || normalized === 'PAYMENT_PENDING') return '결제 대기'
  if (normalized === 'PAID' || normalized === 'READY_TO_SHIP') return '배송 준비'
  if (normalized === 'SHIPPED') return '배송 중'
  if (normalized === 'DELIVERED') return '배송 완료'
  if (normalized === 'CANCELLED') return '주문 취소'
  if (normalized === 'REFUND_PENDING') return '환불 접수'
  if (normalized === 'REFUNDED') return '환불 완료'
  return status
}

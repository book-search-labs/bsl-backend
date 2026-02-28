import { useEffect, useState } from 'react'

import { listVouchers } from '../../services/myService'
import type { VoucherItem } from '../../types/my'

export default function MyVouchersPage() {
  const [items, setItems] = useState<VoucherItem[]>([])

  useEffect(() => {
    let active = true
    listVouchers().then((data) => {
      if (!active) return
      setItems(data)
    })

    return () => {
      active = false
    }
  }, [])

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>e교환권</h1>
        <p>발급된 교환권의 사용 가능 여부와 만료 일정을 확인합니다.</p>
      </header>

      <div className="my-book-grid my-voucher-grid">
        {items.map((item) => (
          <article className="my-voucher-card" key={item.id}>
            <h2>{item.name}</h2>
            <div className="my-voucher-value">{new Intl.NumberFormat('ko-KR').format(item.value)}원</div>
            <div className="my-muted">만료일: {item.expiresAt}</div>
            <span className={`my-badge ${item.used ? 'is-muted' : 'is-active'}`}>
              {item.used ? '사용 완료' : '사용 가능'}
            </span>
          </article>
        ))}
      </div>
    </section>
  )
}

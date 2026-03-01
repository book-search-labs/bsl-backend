import { useEffect, useState } from 'react'

import { listCoupons } from '../../services/myService'
import type { CouponItem } from '../../types/my'

export default function MyCouponsPage() {
  const [items, setItems] = useState<CouponItem[]>([])

  useEffect(() => {
    let active = true
    listCoupons().then((data) => {
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
        <h1>쿠폰</h1>
        <p>할인쿠폰과 프로모션 쿠폰을 사용 가능 상태로 관리하세요.</p>
      </header>

      <div className="my-book-grid my-voucher-grid">
        {items.map((item) => (
          <article className="my-voucher-card" key={item.id}>
            <h2>{item.discountLabel}</h2>
            <div className="my-list-title">{item.name}</div>
            <div className="my-muted">만료일: {item.expiresAt}</div>
            <span className={`my-badge ${item.usable ? 'is-active' : 'is-muted'}`}>
              {item.usable ? '사용 가능' : '만료'}
            </span>
          </article>
        ))}
      </div>
    </section>
  )
}

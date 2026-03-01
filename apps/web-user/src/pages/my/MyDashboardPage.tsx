import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { listOrders, type OrderSummary } from '../../api/orders'
import { listCoupons, listNotifications, listWishlistItems } from '../../services/myService'
import { formatWon, translateOrderStatus } from './myPageUtils'

type DashboardSnapshot = {
  orderCount: number
  latestOrder: OrderSummary | null
  wishlistCount: number
  couponCount: number
  unreadNotifications: number
}

export default function MyDashboardPage() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>({
    orderCount: 0,
    latestOrder: null,
    wishlistCount: 0,
    couponCount: 0,
    unreadNotifications: 0,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const [orders, wishlist, coupons, unreadNotifications] = await Promise.all([
          listOrders(50),
          listWishlistItems(),
          listCoupons(),
          listNotifications('all', true),
        ])
        if (!active) return
        setSnapshot({
          orderCount: orders.length,
          latestOrder: orders[0] ?? null,
          wishlistCount: wishlist.length,
          couponCount: coupons.filter((item) => item.usable).length,
          unreadNotifications: unreadNotifications.length,
        })
      } catch {
        if (!active) return
        setSnapshot((prev) => ({ ...prev, unreadNotifications: 0 }))
      } finally {
        if (active) setLoading(false)
      }
    }

    void load()

    return () => {
      active = false
    }
  }, [])

  const latestOrderStatus = useMemo(() => {
    if (!snapshot.latestOrder) return '주문 내역이 없습니다'
    return translateOrderStatus(snapshot.latestOrder.status)
  }, [snapshot.latestOrder])

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>마이페이지</h1>
        <p>주문, 혜택, 알림 상태를 한 번에 확인하세요.</p>
      </header>

      <div className="my-dashboard-grid">
        <article className="my-metric-card">
          <h2>주문 내역</h2>
          <div className="my-metric-value">{snapshot.orderCount}건</div>
          <div className="my-metric-sub">최근 상태: {latestOrderStatus}</div>
          <Link to="/my/orders" className="my-inline-action">
            주문/배송 보기
          </Link>
        </article>

        <article className="my-metric-card">
          <h2>찜 목록</h2>
          <div className="my-metric-value">{snapshot.wishlistCount}권</div>
          <div className="my-metric-sub">관심 도서를 모아두고 비교하세요.</div>
          <Link to="/my/wishlist" className="my-inline-action">
            찜 보기
          </Link>
        </article>

        <article className="my-metric-card">
          <h2>사용 가능 쿠폰</h2>
          <div className="my-metric-value">{snapshot.couponCount}장</div>
          <div className="my-metric-sub">결제 단계에서 자동 적용됩니다.</div>
          <Link to="/my/wallet/coupons" className="my-inline-action">
            쿠폰 보기
          </Link>
        </article>

        <article className="my-metric-card">
          <h2>읽지 않은 알림</h2>
          <div className="my-metric-value">{snapshot.unreadNotifications}건</div>
          <div className="my-metric-sub">배송/혜택/이벤트 알림을 확인하세요.</div>
          <Link to="/my/notifications" className="my-inline-action">
            알림함 보기
          </Link>
        </article>
      </div>

      <section className="my-panel mt-4">
        <div className="my-panel-header">
          <h2>최근 주문 요약</h2>
          <Link to="/my/orders" className="my-inline-action">
            전체 주문 보기
          </Link>
        </div>

        {loading ? <div className="my-muted">데이터를 불러오는 중입니다...</div> : null}

        {!loading && snapshot.latestOrder ? (
          <div className="my-order-highlight">
            <div>
              <div className="my-order-highlight-label">주문번호 #{snapshot.latestOrder.order_no ?? snapshot.latestOrder.order_id}</div>
              <div className="my-order-highlight-title">{snapshot.latestOrder.primary_item_title ?? '상품 정보 없음'}</div>
            </div>
            <div className="my-order-highlight-meta">
              <span>{translateOrderStatus(snapshot.latestOrder.status)}</span>
              <strong>{formatWon(snapshot.latestOrder.total_amount)}</strong>
            </div>
          </div>
        ) : null}

        {!loading && !snapshot.latestOrder ? <div className="my-empty">주문 내역이 없습니다.</div> : null}
      </section>
    </section>
  )
}

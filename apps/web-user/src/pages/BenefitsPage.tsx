import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { fetchHomeBenefits, type HomeBenefitItem } from '../api/homeBenefits'

function formatPeriod(startAt?: string | null, endAt?: string | null) {
  const start = startAt ? new Date(startAt) : null
  const end = endAt ? new Date(endAt) : null
  const isValidDate = (date: Date | null) => Boolean(date && !Number.isNaN(date.getTime()))
  if (!isValidDate(start) && !isValidDate(end)) return '상시 적용'

  const formatDate = (value: Date | null) =>
    value
      ? `${value.getFullYear()}.${String(value.getMonth() + 1).padStart(2, '0')}.${String(value.getDate()).padStart(2, '0')}`
      : null

  const startText = formatDate(start)
  const endText = formatDate(end)
  if (startText && endText) return `${startText} ~ ${endText}`
  if (startText) return `${startText}부터`
  if (endText) return `${endText}까지`
  return '상시 적용'
}

export default function BenefitsPage() {
  const [items, setItems] = useState<HomeBenefitItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [today, setToday] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setIsLoading(true)
    setErrorMessage(null)

    fetchHomeBenefits(24)
      .then((result) => {
        if (!active) return
        setItems(result.items)
        setToday(result.today)
      })
      .catch(() => {
        if (!active) return
        setItems([])
        setToday(null)
        setErrorMessage('오늘의 혜택을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [])

  const topItems = useMemo(() => items.slice(0, 12), [items])

  return (
    <section className="benefits-page page-section">
      <div className="container">
        <header className="benefits-header">
          <div>
            <h1 className="benefits-title">오늘의 혜택</h1>
            <p className="benefits-note">실시간 프로모션과 결제 혜택을 확인하고 바로 적용하세요.</p>
          </div>
          <div className="benefits-date">{today ? `기준일 ${today}` : '기준일 확인 중'}</div>
        </header>

        {isLoading ? (
          <div className="benefits-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <article key={`benefit-skeleton-${index}`} className="benefit-card benefit-card--skeleton" />
            ))}
          </div>
        ) : errorMessage ? (
          <div className="event-panel-empty">{errorMessage}</div>
        ) : topItems.length === 0 ? (
          <div className="event-panel-empty">현재 적용 가능한 혜택이 없습니다.</div>
        ) : (
          <div className="benefits-grid">
            {topItems.map((item) => (
              <article key={item.item_id} className="benefit-card">
                <div className="benefit-card-head">
                  <span className="benefit-badge">{item.badge ?? '혜택'}</span>
                  <span className="benefit-period">{formatPeriod(item.valid_from, item.valid_to)}</span>
                </div>
                <h2 className="benefit-title">{item.title}</h2>
                {item.description ? <p className="benefit-description">{item.description}</p> : null}
                <div className="benefit-highlight">{item.discount_label ?? '혜택 적용 가능'}</div>
                <div className="benefit-meta">
                  {item.min_order_amount_label ? <span>최소 주문 {item.min_order_amount_label}</span> : null}
                  {typeof item.remaining_daily === 'number' ? <span>오늘 남은 수량 {item.remaining_daily}건</span> : null}
                </div>
                {item.link_url ? (
                  <Link className="btn btn-outline-primary btn-sm" to={item.link_url}>
                    {item.cta_label?.trim() || '혜택 적용하기'}
                  </Link>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

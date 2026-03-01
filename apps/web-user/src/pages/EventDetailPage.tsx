import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { fetchHomePanelDetail, type HomePanelItem } from '../api/homePanels'
import { formatPanelPeriod, resolvePanelBannerUrl, splitPanelDetailBody } from '../utils/homePanels'

function isExternalLink(url: string) {
  return /^https?:\/\//i.test(url)
}

export default function EventDetailPage() {
  const { itemId } = useParams<{ itemId: string }>()
  const [item, setItem] = useState<HomePanelItem | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    const numericId = Number(itemId)
    if (!Number.isFinite(numericId) || numericId <= 0) {
      setItem(null)
      setIsLoading(false)
      setErrorMessage('유효하지 않은 이벤트/공지입니다.')
      return
    }

    let active = true
    setIsLoading(true)
    setErrorMessage(null)
    fetchHomePanelDetail(numericId)
      .then((response) => {
        if (!active) return
        setItem(response)
      })
      .catch(() => {
        if (!active) return
        setItem(null)
        setErrorMessage('이벤트/공지 정보를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [itemId])

  const linkUrl = item?.link_url?.trim()
  const banner = item ? (
    <img
      className="event-banner-image"
      src={resolvePanelBannerUrl(item)}
      alt={`${item.type === 'NOTICE' ? '공지' : '이벤트'} 배너`}
      loading="eager"
    />
  ) : null
  const detailLines = splitPanelDetailBody(item?.detail_body)
  const periodText = item ? formatPanelPeriod(item) : null

  return (
    <section className="events-page page-section">
      <div className="container">
        <h1 className="visually-hidden">이벤트/공지 상세</h1>
        <div className="event-detail-shell">
          {isLoading ? (
            <div className="event-banner-skeleton event-banner-skeleton--single" />
          ) : errorMessage || !item ? (
            <div className="event-panel-empty">{errorMessage ?? '이벤트/공지 정보를 찾을 수 없습니다.'}</div>
          ) : (
            <>
              <div className="event-carousel-link event-carousel-link--center">{banner}</div>
              <article className="event-detail-content">
                <div className="event-detail-badge">{item.type === 'NOTICE' ? '공지' : '이벤트'}</div>
                <h2 className="event-detail-title">{item.title}</h2>
                {item.subtitle ? <p className="event-detail-subtitle">{item.subtitle}</p> : null}
                {item.summary ? <p className="event-detail-summary">{item.summary}</p> : null}
                {periodText ? (
                  <div className="event-detail-meta">
                    <span className="event-detail-meta-label">진행 기간</span>
                    <span>{periodText}</span>
                  </div>
                ) : null}
                {detailLines.length > 0 ? (
                  <ul className="event-detail-list">
                    {detailLines.map((line, index) => (
                      <li key={`${item.item_id}-detail-${index}`}>{line}</li>
                    ))}
                  </ul>
                ) : null}
              </article>
            </>
          )}
          <div className="event-detail-actions">
            {item && linkUrl
              ? isExternalLink(linkUrl)
                ? (
                  <a className="btn btn-primary" href={linkUrl} target="_blank" rel="noreferrer">
                    관련 페이지 이동
                  </a>
                )
                : (
                  <Link to={linkUrl} className="btn btn-primary">
                    관련 페이지 이동
                  </Link>
                )
              : null}
            <Link to="/events" className="btn btn-outline-secondary">
              이벤트/공지 목록
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

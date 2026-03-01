import { useEffect, useState } from 'react'

import {
  listNotificationPreferences,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  setNotificationPreference,
} from '../../services/myService'
import type { MyNotification, NotificationCategory, NotificationPreference } from '../../types/my'
import { formatDateTime } from './myPageUtils'

const notificationCategories: Array<{ key: NotificationCategory | 'all'; label: string }> = [
  { key: 'all', label: '전체' },
  { key: 'order', label: '주문/배송' },
  { key: 'event', label: '이벤트' },
  { key: 'benefit', label: '혜택' },
  { key: 'system', label: '서비스' },
]

export default function MyNotificationsPage() {
  const [filter, setFilter] = useState<NotificationCategory | 'all'>('all')
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [items, setItems] = useState<MyNotification[]>([])
  const [prefs, setPrefs] = useState<NotificationPreference[]>([])

  const load = async (nextFilter: NotificationCategory | 'all', nextUnreadOnly: boolean) => {
    const [notifications, preferences] = await Promise.all([
      listNotifications(nextFilter, nextUnreadOnly),
      listNotificationPreferences(),
    ])
    setItems(notifications)
    setPrefs(preferences)
  }

  useEffect(() => {
    void load(filter, unreadOnly)
  }, [filter, unreadOnly])

  const handleRead = async (id: string) => {
    await markNotificationRead(id)
    void load(filter, unreadOnly)
  }

  const handleMarkAllRead = async () => {
    await markAllNotificationsRead()
    void load(filter, unreadOnly)
  }

  const handleTogglePreference = async (category: NotificationCategory, enabled: boolean) => {
    const next = await setNotificationPreference(category, enabled)
    setPrefs(next)
  }

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>알림함</h1>
        <p>알림 신청 상태를 변경하고 수신 목록을 읽음 처리할 수 있습니다.</p>
      </header>

      <section className="my-panel">
        <div className="my-panel-header">
          <h2 className="my-subtitle">알림 신청</h2>
        </div>
        <div className="my-toggle-grid">
          {prefs.map((pref) => (
            <label key={pref.category} className="my-toggle-card">
              <span>{pref.label}</span>
              <input
                type="checkbox"
                checked={pref.enabled}
                onChange={(event) => handleTogglePreference(pref.category, event.target.checked)}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="my-panel mt-4">
        <div className="my-panel-header">
          <h2 className="my-subtitle">수신 알림</h2>
          <button className="btn btn-sm btn-outline-secondary" type="button" onClick={handleMarkAllRead}>
            전체 읽음 처리
          </button>
        </div>

        <div className="my-chip-row mb-3">
          {notificationCategories.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`my-chip ${filter === item.key ? 'is-active' : ''}`}
              onClick={() => setFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
          <label className="my-checkbox-inline">
            <input type="checkbox" checked={unreadOnly} onChange={(event) => setUnreadOnly(event.target.checked)} />
            안 읽은 알림만
          </label>
        </div>

        {items.length === 0 ? (
          <div className="my-empty">조건에 맞는 알림이 없습니다.</div>
        ) : (
          <div className="my-notification-list">
            {items.map((item) => (
              <article className={`my-notification-card ${item.read ? 'is-read' : ''}`} key={item.id}>
                <div>
                  <div className="my-list-title">{item.title}</div>
                  <p>{item.body}</p>
                  <small>{formatDateTime(item.createdAt)}</small>
                </div>
                {item.read ? (
                  <span className="my-badge is-muted">읽음</span>
                ) : (
                  <button type="button" className="btn btn-sm btn-primary" onClick={() => handleRead(item.id)}>
                    읽음 처리
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}

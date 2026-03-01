import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listGiftItems } from '../../services/myService'
import type { MyGiftItem } from '../../types/my'

export default function MyGiftsPage() {
  const [items, setItems] = useState<MyGiftItem[]>([])

  useEffect(() => {
    let active = true
    listGiftItems().then((data) => {
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
        <h1>선물함</h1>
        <p>주고받은 선물 도서를 상태별로 관리할 수 있습니다.</p>
      </header>

      <section className="my-panel">
        {items.length === 0 ? <div className="my-empty">선물 내역이 없습니다.</div> : null}
        {items.length > 0 ? (
          <div className="my-list-table">
            {items.map((item) => (
              <div key={item.id} className="my-list-row">
                <div>
                  <div className="my-list-title">{item.title}</div>
                  <div className="my-list-sub">{new Date(item.createdAt).toLocaleDateString('ko-KR')}</div>
                </div>
                <div className="my-list-meta">{item.status}</div>
                <Link to={`/my/gifts/${item.id}`} className="btn btn-sm btn-outline-secondary">
                  상세 보기
                </Link>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </section>
  )
}

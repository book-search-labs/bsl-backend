import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import BookCover from '../../components/books/BookCover'
import { listWishlistItems, removeWishlistItem } from '../../services/myService'
import type { WishlistItem } from '../../types/my'
import { formatWon } from './myPageUtils'

export default function MyWishlistPage() {
  const [items, setItems] = useState<WishlistItem[]>([])
  const [removingDocId, setRemovingDocId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    listWishlistItems().then((data) => {
      if (!active) return
      setItems(data)
    })

    return () => {
      active = false
    }
  }, [])

  const handleRemove = async (docId: string) => {
    try {
      setRemovingDocId(docId)
      setMessage(null)
      const next = await removeWishlistItem(docId)
      setItems(next)
      setMessage('찜 목록에서 삭제했습니다.')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '찜 삭제에 실패했습니다.')
    } finally {
      setRemovingDocId(null)
    }
  }

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>찜(위시리스트)</h1>
        <p>관심 도서를 저장하고 가격/재고 변동을 빠르게 확인하세요.</p>
      </header>
      {message ? <div className="small mb-2">{message}</div> : null}

      {items.length === 0 ? (
        <div className="my-panel my-empty">찜한 도서가 없습니다.</div>
      ) : (
        <div className="my-book-grid">
          {items.map((item) => (
            <article key={item.id} className="my-book-card">
              <BookCover
                title={item.title}
                coverUrl={item.coverUrl}
                docId={item.docId}
                className="my-book-cover"
                size="M"
              />
              <div className="my-book-meta">
                <Link to={`/book/${encodeURIComponent(item.docId)}`} className="my-book-title">
                  {item.title}
                </Link>
                <div className="my-book-author">{item.author}</div>
                <strong>{formatWon(item.price)}</strong>
                <div className="d-flex gap-2 mt-1">
                  <Link to={`/book/${encodeURIComponent(item.docId)}`} className="btn btn-sm btn-outline-secondary">
                    상세 보기
                  </Link>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={() => handleRemove(item.docId)}
                    disabled={removingDocId === item.docId}
                  >
                    {removingDocId === item.docId ? '삭제 중...' : '찜 삭제'}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

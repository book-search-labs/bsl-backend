import { useEffect, useState } from 'react'

import BookCover from '../../components/books/BookCover'
import { listELibraryBooks } from '../../services/myService'
import type { ELibraryBook } from '../../types/my'

export default function MyELibraryPage() {
  const [books, setBooks] = useState<ELibraryBook[]>([])

  useEffect(() => {
    let active = true
    listELibraryBooks().then((items) => {
      if (!active) return
      setBooks(items)
    })

    return () => {
      active = false
    }
  }, [])

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>e-라이브러리</h1>
        <p>전자책 보관함과 다운로드 이력을 확인합니다. DRM 정책을 준수하여 열람됩니다.</p>
      </header>

      <section className="my-panel">
        <div className="my-muted">
          전자책은 라이선스와 DRM 정책에 따라 기기 등록 수, 오프라인 기간, 재다운로드 횟수가 제한됩니다.
        </div>
      </section>

      {books.length === 0 ? (
        <section className="my-panel mt-3 my-empty">보관 중인 전자책이 없습니다.</section>
      ) : (
        <div className="my-book-grid mt-3">
          {books.map((book) => (
            <article key={book.id} className="my-book-card">
              <BookCover
                title={book.title}
                coverUrl={book.coverUrl}
                docId={book.id}
                size="M"
                className="my-book-cover"
              />
              <div className="my-book-meta">
                <strong>{book.title}</strong>
                <div>{book.author}</div>
                <div className="my-muted">{book.publisher}</div>
                <div className="my-muted">다운로드: {new Date(book.downloadedAt).toLocaleDateString('ko-KR')}</div>
                <div className="my-badge">{book.drmPolicy}</div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

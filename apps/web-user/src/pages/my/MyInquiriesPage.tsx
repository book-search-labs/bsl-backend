import { useEffect, useState } from 'react'

import { createInquiry, listInquiries } from '../../services/myService'
import type { MyInquiry } from '../../types/my'

export default function MyInquiriesPage() {
  const [items, setItems] = useState<MyInquiry[]>([])
  const [category, setCategory] = useState('주문/배송')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    listInquiries().then((data) => {
      if (!active) return
      setItems(data)
    })

    return () => {
      active = false
    }
  }, [])

  const handleSubmit = async () => {
    if (!title.trim() || !content.trim()) {
      setNotice('제목과 내용을 입력해 주세요.')
      return
    }

    const next = await createInquiry({ title: title.trim(), category, content: content.trim() })
    setItems((prev) => [next, ...prev])
    setTitle('')
    setContent('')
    setNotice('문의가 접수되었습니다.')
  }

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>1:1 문의</h1>
        <p>문의를 등록하면 상태(접수/처리 중/답변 완료)로 진행 내역을 확인할 수 있습니다.</p>
      </header>

      <section className="my-panel">
        <h2 className="my-subtitle">문의 등록</h2>
        <div className="my-form-grid">
          <label>
            문의 유형
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option>주문/배송</option>
              <option>결제/환불</option>
              <option>쿠폰/혜택</option>
              <option>계정/설정</option>
            </select>
          </label>
          <label>
            제목
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="문의 제목" />
          </label>
          <label>
            내용
            <textarea value={content} onChange={(event) => setContent(event.target.value)} rows={5} />
          </label>
          <button type="button" className="btn btn-primary align-self-start" onClick={handleSubmit}>
            문의 접수
          </button>
          {notice ? <div className="my-notice">{notice}</div> : null}
        </div>
      </section>

      <section className="my-panel mt-4">
        <h2 className="my-subtitle">문의 내역</h2>
        {items.length === 0 ? <div className="my-empty">등록된 문의가 없습니다.</div> : null}

        {items.length > 0 ? (
          <div className="my-list-table">
            {items.map((item) => (
              <div key={item.id} className="my-list-row">
                <div>
                  <div className="my-list-title">{item.title}</div>
                  <div className="my-list-sub">
                    {item.category} · {new Date(item.createdAt).toLocaleString('ko-KR')}
                  </div>
                </div>
                <div className="my-list-meta">{item.status}</div>
                <button type="button" className="btn btn-sm btn-outline-secondary">
                  상세
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </section>
  )
}

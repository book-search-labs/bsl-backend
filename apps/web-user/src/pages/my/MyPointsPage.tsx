import { useEffect, useMemo, useState } from 'react'

import { listPointLogs } from '../../services/myService'
import type { WalletPointLog } from '../../types/my'

export default function MyPointsPage() {
  const [logs, setLogs] = useState<WalletPointLog[]>([])

  useEffect(() => {
    let active = true
    listPointLogs().then((items) => {
      if (!active) return
      setLogs(items)
    })

    return () => {
      active = false
    }
  }, [])

  const pointBalance = useMemo(() => logs.reduce((sum, item) => sum + item.amount, 0), [logs])

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>통합포인트</h1>
        <p>적립 및 사용 내역을 관리하고 잔여 포인트를 확인할 수 있습니다.</p>
      </header>

      <section className="my-panel my-balance-panel">
        <span>보유 포인트</span>
        <strong>{new Intl.NumberFormat('ko-KR').format(pointBalance)}P</strong>
      </section>

      <section className="my-panel mt-3">
        {logs.length === 0 ? (
          <div className="my-empty">포인트 변동 내역이 없습니다.</div>
        ) : (
          <div className="my-list-table">
            {logs.map((item) => (
              <div className="my-list-row" key={item.id}>
                <div>
                  <div className="my-list-title">{item.description}</div>
                  <div className="my-list-sub">{new Date(item.createdAt).toLocaleString('ko-KR')}</div>
                </div>
                <div className={`my-list-meta ${item.amount > 0 ? 'is-positive' : ''}`}>
                  {item.amount > 0 ? '+' : ''}
                  {new Intl.NumberFormat('ko-KR').format(item.amount)}P
                </div>
                <span className="my-muted">반영 완료</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}

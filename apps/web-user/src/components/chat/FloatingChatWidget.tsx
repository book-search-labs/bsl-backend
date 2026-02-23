import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { streamChat, submitChatFeedback, type ChatSource, type ChatStreamMeta } from '../../api/chat'
import { OPEN_FLOATING_CHAT_EVENT, type OpenFloatingChatDetail } from './chatWidgetEvents'

type ChatBubble = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  citations?: string[]
  status?: string
  riskBand?: string
  reasonCode?: string
  recoverable?: boolean
  nextAction?: string
  retryAfterMs?: number | null
  fallbackCount?: number
  escalated?: boolean
}

const CHAT_HISTORY_LIMIT = 8

function uuid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function statusLabel(status?: string) {
  if (!status) return '응답 확인 중'
  if (status === 'ok') return '정상 응답'
  if (status === 'cached') return '빠른 응답'
  if (status === 'streaming') return '응답 생성 중'
  if (status === 'insufficient_evidence') return '근거 부족'
  if (status === 'guard_blocked') return '안전 가드 제한'
  if (status === 'error') return '오류'
  return status
}

function riskLabel(riskBand?: string) {
  if (!riskBand) return null
  if (riskBand === 'R0') return '위험도 낮음'
  if (riskBand === 'R1') return '위험도 보통'
  if (riskBand === 'R2') return '위험도 주의'
  if (riskBand === 'R3') return '위험도 높음'
  return `위험도 ${riskBand}`
}

function looksLikeInsufficientMessage(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return true
  return normalized.includes('insufficient evidence')
}

function nextActionLabel(action?: string) {
  if (!action || action === 'NONE' || action === 'WAIT') return null
  if (action === 'RETRY') return '잠시 후 다시 시도해 주세요.'
  if (action === 'REFINE_QUERY') return '질문을 더 구체적으로 입력해 주세요.'
  if (action === 'LOGIN_REQUIRED') return '로그인 후 다시 시도해 주세요.'
  if (action === 'PROVIDE_REQUIRED_INFO') return '주문번호/티켓번호 같은 필수 정보를 입력해 주세요.'
  if (action === 'CONFIRM_ACTION') return '확인 코드를 포함해 승인 메시지를 입력해 주세요.'
  if (action === 'OPEN_SUPPORT_TICKET') return '상담 문의 접수로 전환해 주세요.'
  return null
}

function nextActionPrompt(action?: string) {
  if (!action) return null
  if (action === 'OPEN_SUPPORT_TICKET') return '문의 접수해줘'
  if (action === 'REFINE_QUERY') return '질문을 더 구체적으로 다시 입력할게'
  if (action === 'RETRY') return '다시 시도해줘'
  return null
}

export default function FloatingChatWidget() {
  const location = useLocation()
  const sessionIdRef = useRef(uuid())
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<ChatBubble[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const prompts = useMemo(() => {
    const base = ['배송 정책을 알려줘', '환불 조건을 정리해줘', '장바구니 기준 추천해줘']
    if (location.pathname.startsWith('/book/')) {
      return ['이 책과 비슷한 도서 추천해줘', ...base]
    }
    if (location.pathname.startsWith('/cart')) {
      return ['장바구니 도서 기준으로 추천해줘', ...base]
    }
    if (location.pathname.startsWith('/orders')) {
      return ['주문 상태별 취소/반품 규정을 알려줘', ...base]
    }
    return base
  }, [location.pathname])

  const send = useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || streaming) return

    const userMessage: ChatBubble = { id: uuid(), role: 'user', content: trimmed }
    const assistantId = uuid()
    const assistantMessage: ChatBubble = { id: assistantId, role: 'assistant', content: '', status: 'streaming' }

    setMessages((prev) => [...prev, userMessage, assistantMessage])
    setInput('')
    setError(null)
    setStreaming(true)

    try {
      await streamChat(
        {
          version: 'v1',
          session_id: sessionIdRef.current,
          message: { role: 'user', content: trimmed },
          history: messages.slice(-CHAT_HISTORY_LIMIT).map((item) => ({ role: item.role, content: item.content })),
          options: { stream: true, top_k: 6 },
        },
        {
          onMeta: (meta: ChatStreamMeta) => {
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      status: typeof meta.status === 'string' ? meta.status : item.status,
                      sources: Array.isArray(meta.sources) ? meta.sources : item.sources,
                      citations: Array.isArray(meta.citations) ? meta.citations : item.citations,
                      riskBand: typeof meta.risk_band === 'string' ? meta.risk_band : item.riskBand,
                      reasonCode: typeof meta.reason_code === 'string' ? meta.reason_code : item.reasonCode,
                      recoverable: typeof meta.recoverable === 'boolean' ? meta.recoverable : item.recoverable,
                      nextAction: typeof meta.next_action === 'string' ? meta.next_action : item.nextAction,
                      retryAfterMs: typeof meta.retry_after_ms === 'number' || meta.retry_after_ms === null ? meta.retry_after_ms : item.retryAfterMs,
                      fallbackCount: typeof meta.fallback_count === 'number' ? meta.fallback_count : item.fallbackCount,
                      escalated: typeof meta.escalated === 'boolean' ? meta.escalated : item.escalated,
                    }
                  : item,
              ),
            )
          },
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((item) => (item.id === assistantId ? { ...item, content: `${item.content}${token}` } : item)),
            )
          },
          onDone: (done) => {
            setMessages((prev) =>
              prev.map((item) => {
                if (item.id !== assistantId) return item
                const nextStatus = typeof done.status === 'string' ? done.status : item.status
                const nextContent =
                  nextStatus === 'insufficient_evidence' && looksLikeInsufficientMessage(item.content)
                    ? '현재 근거 문서가 부족해 확정 답변을 드리기 어렵습니다. 질문을 더 구체적으로 입력해 주세요. (예: 주문취소 수수료, 배송비, 환불 기간)'
                    : item.content || '답변을 생성하지 못했습니다. 다시 시도해 주세요.'
                return {
                  ...item,
                  status: nextStatus,
                  citations: Array.isArray(done.citations) ? done.citations : item.citations,
                  riskBand: typeof done.risk_band === 'string' ? done.risk_band : item.riskBand,
                  reasonCode: typeof done.reason_code === 'string' ? done.reason_code : item.reasonCode,
                  recoverable: typeof done.recoverable === 'boolean' ? done.recoverable : item.recoverable,
                  nextAction: typeof done.next_action === 'string' ? done.next_action : item.nextAction,
                  retryAfterMs:
                    typeof done.retry_after_ms === 'number' || done.retry_after_ms === null ? done.retry_after_ms : item.retryAfterMs,
                  fallbackCount: typeof done.fallback_count === 'number' ? done.fallback_count : item.fallbackCount,
                  escalated: typeof done.escalated === 'boolean' ? done.escalated : item.escalated,
                  content: nextContent,
                }
              }),
            )
          },
          onError: (streamError) => {
            setError(streamError?.message ?? '챗봇 응답 처리 중 오류가 발생했습니다.')
          },
        },
      )
    } catch {
      setError('챗봇 응답을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setStreaming(false)
    }
  }, [input, messages, streaming])

  const submitFeedback = useCallback(async (messageId: string, rating: 'up' | 'down') => {
    await submitChatFeedback({
      version: 'v1',
      session_id: sessionIdRef.current,
      message_id: messageId,
      rating,
    })
  }, [])

  useEffect(() => {
    if (!isOpen) return
    const timer = window.setTimeout(() => {
      inputRef.current?.focus()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [isOpen])

  useEffect(() => {
    const handleOpen = (event: Event) => {
      const customEvent = event as CustomEvent<OpenFloatingChatDetail>
      const prompt = customEvent.detail?.prompt?.trim()
      setIsOpen(true)
      if (prompt) {
        setInput(prompt)
      }
      window.setTimeout(() => {
        inputRef.current?.focus()
      }, 0)
    }

    window.addEventListener(OPEN_FLOATING_CHAT_EVENT, handleOpen as EventListener)
    return () => {
      window.removeEventListener(OPEN_FLOATING_CHAT_EVENT, handleOpen as EventListener)
    }
  }, [])

  return (
    <div className="floating-chat-widget" aria-live="polite">
      {isOpen ? (
        <section className="floating-chat-panel" aria-label="고정 챗봇">
          <header className="floating-chat-header">
            <div>
              <div className="floating-chat-title">책봇</div>
              <div className="floating-chat-subtitle">주문/배송/환불/추천 상담</div>
            </div>
            <button type="button" className="floating-chat-close" onClick={() => setIsOpen(false)} aria-label="챗봇 닫기">
              닫기
            </button>
          </header>

          <div className="floating-chat-body">
            {messages.length === 0 ? (
              <div className="floating-chat-empty">
                <div className="floating-chat-empty-title">무엇을 도와드릴까요?</div>
                <div className="floating-chat-prompt-list">
                  {prompts.map((prompt) => (
                    <button key={prompt} type="button" className="floating-chat-prompt" onClick={() => setInput(prompt)}>
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="floating-chat-thread">
                {messages.map((message) => (
                  <article key={message.id} className={`floating-chat-bubble ${message.role}`}>
                    <div className="floating-chat-role">{message.role === 'user' ? '나' : '책봇'}</div>
                    {message.role === 'assistant' ? (
                      <div className="floating-chat-badges">
                        <span className="floating-chat-badge">{statusLabel(message.status)}</span>
                        {riskLabel(message.riskBand) ? <span className="floating-chat-badge muted">{riskLabel(message.riskBand)}</span> : null}
                      </div>
                    ) : null}
                    <div className="floating-chat-content">{message.content || '...'}</div>
                    {message.role === 'assistant' && nextActionLabel(message.nextAction) ? (
                      <div className="floating-chat-action-hint">
                        {nextActionLabel(message.nextAction)}
                        {message.retryAfterMs && message.retryAfterMs > 0 ? ` (${Math.ceil(message.retryAfterMs / 1000)}초 후)` : ''}
                        {typeof message.fallbackCount === 'number' && message.fallbackCount > 0 ? ` · 실패 누적 ${message.fallbackCount}회` : ''}
                      </div>
                    ) : null}
                    {message.role === 'assistant' && message.escalated && nextActionPrompt(message.nextAction) ? (
                      <button type="button" className="floating-chat-action-btn" onClick={() => setInput(nextActionPrompt(message.nextAction) ?? '')}>
                        상담 전환 진행
                      </button>
                    ) : null}
                    {message.role === 'assistant' && message.sources && message.sources.length > 0 ? (
                      <details className="floating-chat-sources">
                        <summary>근거 출처 {message.sources.length}건</summary>
                        <ul>
                          {message.sources.map((source) => (
                            <li key={source.citation_key}>
                              <strong>{source.title || source.doc_id}</strong>
                              <p>{source.snippet}</p>
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                    {message.role === 'assistant' ? (
                      <div className="floating-chat-feedback">
                        <button type="button" onClick={() => submitFeedback(message.id, 'up')}>
                          👍
                        </button>
                        <button type="button" onClick={() => submitFeedback(message.id, 'down')}>
                          👎
                        </button>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </div>

          <footer className="floating-chat-footer">
            {error ? <div className="floating-chat-error">{error}</div> : null}
            <form
              className="floating-chat-form"
              onSubmit={(event) => {
                event.preventDefault()
                void send()
              }}
            >
              <input
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="질문을 입력하세요"
                disabled={streaming}
              />
              <button type="submit" disabled={streaming || !input.trim()}>
                {streaming ? '...' : '전송'}
              </button>
            </form>
          </footer>
        </section>
      ) : null}

      <button
        type="button"
        className="floating-chat-launcher"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label={isOpen ? '챗봇 닫기' : '챗봇 열기'}
      >
        {isOpen ? '닫기' : '책봇'}
      </button>
    </div>
  )
}

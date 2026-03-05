import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Card, Col, Form, Row, Spinner } from 'react-bootstrap'
import { useNavigate } from 'react-router-dom'

import { streamChat, submitChatFeedback, type ChatSource, type ChatStreamMeta } from '../api/chat'
import { parseChatBookCandidates } from '../components/chat/bookCandidates'
import { CHAT_COMMAND_CATALOG } from '../components/chat/commandCatalog'
import { parseChatOrderCandidates } from '../components/chat/orderCandidates'

const DEFAULT_PROMPTS = [
  '배송 정책을 알려줘',
  '환불 조건을 정리해줘',
  '멤버십 혜택을 요약해줘',
]

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

function uuid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function statusBadgeVariant(status?: string) {
  if (!status) return 'text-bg-secondary'
  if (status === 'ok' || status === 'cached' || status === 'streaming') return 'text-bg-success'
  if (status === 'insufficient_evidence' || status === 'guard_blocked') return 'text-bg-warning'
  return 'text-bg-danger'
}

function statusLabel(status?: string) {
  if (!status) return '상태 미확인'
  if (status === 'ok') return '정상 응답'
  if (status === 'cached') return '캐시 응답'
  if (status === 'streaming') return '응답 생성 중'
  if (status === 'insufficient_evidence') return '근거 부족'
  if (status === 'guard_blocked') return '안전 가드 제한'
  if (status === 'error') return '오류'
  return status
}

function riskBandLabel(riskBand?: string) {
  if (!riskBand) return null
  if (riskBand === 'R0') return '위험도 낮음'
  if (riskBand === 'R1') return '위험도 보통'
  if (riskBand === 'R2') return '위험도 주의'
  if (riskBand === 'R3') return '위험도 높음'
  return `위험도 ${riskBand}`
}

function nextActionHint(action?: string, retryAfterMs?: number | null) {
  if (!action || action === 'NONE' || action === 'WAIT') return null
  const retryText = retryAfterMs && retryAfterMs > 0 ? ` (${Math.ceil(retryAfterMs / 1000)}초 후)` : ''
  if (action === 'RETRY') return `잠시 후 다시 시도해 주세요.${retryText}`
  if (action === 'REFINE_QUERY') return '질문을 더 구체적으로 입력해 주세요.'
  if (action === 'LOGIN_REQUIRED') return '로그인 후 다시 시도해 주세요.'
  if (action === 'PROVIDE_REQUIRED_INFO') return '주문번호/티켓번호 같은 필수 정보를 입력해 주세요.'
  if (action === 'CONFIRM_ACTION') return '확인 코드를 포함해 승인 메시지를 입력해 주세요.'
  if (action === 'OPEN_SUPPORT_TICKET') return '상담 문의 접수로 전환해 주세요.'
  return null
}

function nextActionPrompt(action?: string) {
  if (action === 'OPEN_SUPPORT_TICKET') return '문의 접수해줘'
  if (action === 'RETRY') return '다시 시도해줘'
  if (action === 'REFINE_QUERY') return '질문을 더 구체적으로 다시 입력할게'
  return null
}

export default function ChatPage() {
  const navigate = useNavigate()
  const sessionIdRef = useRef(uuid())
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const [messages, setMessages] = useState<ChatBubble[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSend = useCallback(async (presetInput?: string) => {
    const rawInput = typeof presetInput === 'string' ? presetInput : input
    const trimmed = rawInput.trim()
    if (!trimmed || isStreaming) return

    const userMessage: ChatBubble = { id: uuid(), role: 'user', content: trimmed }
    const assistantMessage: ChatBubble = { id: uuid(), role: 'assistant', content: '' }

    setMessages((prev) => [...prev, userMessage, assistantMessage])
    setInput('')
    setError(null)
    setIsStreaming(true)

    try {
      await streamChat(
        {
          version: 'v1',
          session_id: sessionIdRef.current,
          message: { role: 'user', content: trimmed },
          history: messages.map((message) => ({ role: message.role, content: message.content })),
          options: { stream: true },
        },
        {
          onMeta: (response: ChatStreamMeta) => {
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantMessage.id
                  ? {
                      ...item,
                      sources: Array.isArray(response.sources) ? response.sources : item.sources,
                      citations: Array.isArray(response.citations) ? response.citations : item.citations,
                      status: typeof response.status === 'string' ? response.status : item.status,
                      riskBand: typeof response.risk_band === 'string' ? response.risk_band : item.riskBand,
                      reasonCode: typeof response.reason_code === 'string' ? response.reason_code : item.reasonCode,
                      recoverable: typeof response.recoverable === 'boolean' ? response.recoverable : item.recoverable,
                      nextAction: typeof response.next_action === 'string' ? response.next_action : item.nextAction,
                      retryAfterMs:
                        typeof response.retry_after_ms === 'number' || response.retry_after_ms === null
                          ? response.retry_after_ms
                          : item.retryAfterMs,
                      fallbackCount: typeof response.fallback_count === 'number' ? response.fallback_count : item.fallbackCount,
                      escalated: typeof response.escalated === 'boolean' ? response.escalated : item.escalated,
                    }
                  : item,
              ),
            )
          },
          onToken: (token: string) => {
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantMessage.id
                  ? { ...item, content: `${item.content}${token}` }
                  : item,
              ),
            )
          },
          onDone: (done) => {
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantMessage.id
                  ? {
                      ...item,
                      status: typeof done.status === 'string' ? done.status : item.status,
                      citations: Array.isArray(done.citations) ? done.citations : item.citations,
                      riskBand: typeof done.risk_band === 'string' ? done.risk_band : item.riskBand,
                      reasonCode: typeof done.reason_code === 'string' ? done.reason_code : item.reasonCode,
                      recoverable: typeof done.recoverable === 'boolean' ? done.recoverable : item.recoverable,
                      nextAction: typeof done.next_action === 'string' ? done.next_action : item.nextAction,
                      retryAfterMs:
                        typeof done.retry_after_ms === 'number' || done.retry_after_ms === null
                          ? done.retry_after_ms
                          : item.retryAfterMs,
                      fallbackCount: typeof done.fallback_count === 'number' ? done.fallback_count : item.fallbackCount,
                      escalated: typeof done.escalated === 'boolean' ? done.escalated : item.escalated,
                    }
                  : item,
              ),
            )
          },
          onError: (streamError) => {
            if (streamError?.message) {
              setError(streamError.message)
            }
          },
        },
      )
    } catch {
      setError('챗봇 응답을 불러오지 못했습니다.')
    } finally {
      setIsStreaming(false)
    }
  }, [input, isStreaming, messages])

  const handleFeedback = useCallback(
    async (messageId: string, rating: 'up' | 'down', flags?: { hallucination?: boolean; insufficient?: boolean }) => {
      await submitChatFeedback({
        version: 'v1',
        session_id: sessionIdRef.current,
        message_id: messageId,
        rating,
        flag_hallucination: flags?.hallucination ?? false,
        flag_insufficient: flags?.insufficient ?? false,
      })
    },
    [],
  )

  useEffect(() => {
    const body = bodyRef.current
    if (!body) return
    body.scrollTop = body.scrollHeight
  }, [messages])

  return (
    <div className="chat-page">
      <Row className="gy-4">
        <Col lg={8}>
          <Card className="chat-card">
            <Card.Body ref={bodyRef} className="chat-body">
              {messages.length === 0 ? (
                <div className="chat-empty">
                  <h2>근거 기반 도서 도우미</h2>
                  <p>근거 문서가 확인된 경우에만 답변을 제공합니다.</p>
                  <div className="chat-prompts">
                    {DEFAULT_PROMPTS.map((prompt) => (
                      <Button key={prompt} variant="outline-dark" onClick={() => void handleSend(prompt)}>
                        {prompt}
                      </Button>
                    ))}
                  </div>
                  <div className="chat-command-guide">
                    <div className="chat-command-guide-title">가능한 명령어 예시</div>
                    <div className="chat-command-guide-grid">
                      {CHAT_COMMAND_CATALOG.map((category) => (
                        <div key={category.title} className="chat-command-card">
                          <div className="chat-command-card-title">{category.title}</div>
                          <div className="chat-command-card-list">
                            {category.examples.map((example) => (
                              <Button
                                key={`${category.title}-${example}`}
                                size="sm"
                                variant="outline-secondary"
                                onClick={() => void handleSend(example)}
                              >
                                {example}
                              </Button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="chat-thread">
                  {messages.map((message) => {
                    const bookCandidates = message.role === 'assistant' ? parseChatBookCandidates(message.content) : []
                    const orderCandidates = message.role === 'assistant' ? parseChatOrderCandidates(message.content) : []
                    return (
                      <div key={message.id} className={`chat-bubble ${message.role}`}>
                        <div className="chat-bubble-inner">
                          <div className="chat-role">{message.role === 'user' ? '나' : '챗봇'}</div>
                          {message.role === 'assistant' ? (
                            <div className="d-flex flex-wrap gap-2 mb-2">
                              <span className={`badge ${statusBadgeVariant(message.status)}`}>{statusLabel(message.status)}</span>
                              {riskBandLabel(message.riskBand) ? (
                                <span className="badge text-bg-light border">{riskBandLabel(message.riskBand)}</span>
                              ) : null}
                            </div>
                          ) : null}
                          <div className="chat-content">{message.content || (message.role === 'assistant' ? '...' : '')}</div>
                          {message.role === 'assistant' && bookCandidates.length > 0 ? (
                            <div className="chat-book-links">
                              <div className="chat-book-links-title">도서 상세 바로가기</div>
                              <div className="chat-book-link-list">
                                {bookCandidates.map((candidate) => (
                                  <button
                                    key={`${message.id}-${candidate.docId}`}
                                    type="button"
                                    className="chat-book-link-btn"
                                    onClick={() => {
                                      navigate(`/book/${encodeURIComponent(candidate.docId)}?from=chat`)
                                    }}
                                  >
                                    <span className="chat-book-link-title">
                                      {candidate.rank ? `${candidate.rank}) ` : ''}
                                      {candidate.title}
                                    </span>
                                    <span className="chat-book-link-meta">
                                      {candidate.author ? `${candidate.author} · ` : ''}
                                      {candidate.docId}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          {message.role === 'assistant' && orderCandidates.length > 0 ? (
                            <div className="chat-order-links">
                              <div className="chat-order-links-title">주문 상세 바로가기</div>
                              <div className="chat-order-link-list">
                                {orderCandidates.map((candidate) => (
                                  <button
                                    key={`${message.id}-order-${candidate.orderId}`}
                                    type="button"
                                    className="chat-order-link-btn"
                                    onClick={() => {
                                      navigate(`/orders/${candidate.orderId}?from=chat`)
                                    }}
                                  >
                                    <span className="chat-order-link-title">
                                      {candidate.rank ? `${candidate.rank}) ` : ''}
                                      {candidate.orderNo || `주문ID ${candidate.orderId}`}
                                    </span>
                                    <span className="chat-order-link-meta">
                                      {[candidate.status, candidate.amount, `주문ID ${candidate.orderId}`].filter(Boolean).join(' · ')}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          {message.role === 'assistant' && nextActionHint(message.nextAction, message.retryAfterMs) ? (
                            <div className="chat-note">
                              {nextActionHint(message.nextAction, message.retryAfterMs)}
                              {typeof message.fallbackCount === 'number' && message.fallbackCount > 0
                                ? ` · 실패 누적 ${message.fallbackCount}회`
                                : ''}
                            </div>
                          ) : null}
                          {message.role === 'assistant' && message.escalated && nextActionPrompt(message.nextAction) ? (
                            <div className="chat-feedback">
                              <Button
                                size="sm"
                                variant="outline-primary"
                                onClick={() => void handleSend(nextActionPrompt(message.nextAction) ?? '')}
                              >
                                상담 전환 진행
                              </Button>
                            </div>
                          ) : null}
                          {message.role === 'assistant' && message.sources && message.sources.length > 0 ? (
                            <div className="chat-sources">
                              <div className="chat-sources-title">근거 출처</div>
                              <div className="chat-sources-grid">
                                {message.sources.map((source) => (
                                  <div key={source.citation_key} className="chat-source-card">
                                    <div className="chat-source-title">{source.title || source.doc_id}</div>
                                    <div className="chat-source-snippet">{source.snippet}</div>
                                    {source.url ? (
                                      <a href={source.url} target="_blank" rel="noreferrer">
                                        보기
                                      </a>
                                    ) : null}
                                    <div className="chat-source-cite">[{source.citation_key}]</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          {message.role === 'assistant' ? (
                            <div className="chat-feedback">
                              <Button
                                size="sm"
                                variant="outline-success"
                                onClick={() => handleFeedback(message.id, 'up')}
                              >
                                👍
                              </Button>
                              <Button
                                size="sm"
                                variant="outline-danger"
                                onClick={() => handleFeedback(message.id, 'down', { hallucination: true })}
                              >
                                👎
                              </Button>
                              <Button
                                size="sm"
                                variant="outline-secondary"
                                onClick={() => handleFeedback(message.id, 'down', { insufficient: true })}
                              >
                                근거 부족
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card.Body>
            <Card.Footer className="chat-footer">
              {error ? <div className="chat-error">{error}</div> : null}
              <Form
                onSubmit={(event) => {
                  event.preventDefault()
                  handleSend()
                }}
              >
                <Form.Group className="d-flex gap-2">
                  <Form.Control
                    value={input}
                    placeholder="질문을 입력하세요"
                    onChange={(event) => setInput(event.target.value)}
                  />
                  <Button type="submit" disabled={isStreaming}>
                    {isStreaming ? <Spinner size="sm" /> : '보내기'}
                  </Button>
                </Form.Group>
              </Form>
            </Card.Footer>
          </Card>
        </Col>
        <Col lg={4}>
          <Card className="chat-side">
            <Card.Body>
                  <h3>응답 기준</h3>
                  <p>모든 답변은 근거 문서를 기반으로 검증됩니다.</p>
                  <ul>
                <li>근거가 부족하면 확정 답변을 제한합니다.</li>
                <li>출처 카드에서 근거를 직접 확인할 수 있습니다.</li>
                <li>피드백은 챗봇 품질 개선에 반영됩니다.</li>
              </ul>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

import { useCallback, useRef, useState } from 'react'
import { Button, Card, Col, Form, Row, Spinner } from 'react-bootstrap'

import { streamChat, submitChatFeedback, type ChatSource, type ChatStreamMeta } from '../api/chat'

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

export default function ChatPage() {
  const sessionIdRef = useRef(uuid())
  const [messages, setMessages] = useState<ChatBubble[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSend = useCallback(async () => {
    const trimmed = input.trim()
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
    } catch (err) {
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

  return (
    <div className="chat-page">
      <Row className="gy-4">
        <Col lg={8}>
          <Card className="chat-card">
            <Card.Body className="chat-body">
              {messages.length === 0 ? (
                <div className="chat-empty">
                  <h2>근거 기반 도서 도우미</h2>
                  <p>근거 문서가 확인된 경우에만 답변을 제공합니다.</p>
                  <div className="chat-prompts">
                    {DEFAULT_PROMPTS.map((prompt) => (
                      <Button key={prompt} variant="outline-dark" onClick={() => setInput(prompt)}>
                        {prompt}
                      </Button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="chat-thread">
                  {messages.map((message) => (
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
                  ))}
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

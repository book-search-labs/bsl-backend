import { useCallback, useRef, useState } from 'react'
import { Button, Card, Col, Form, Row, Spinner } from 'react-bootstrap'

import { streamChat, submitChatFeedback, type ChatResponse, type ChatSource } from '../api/chat'

const DEFAULT_PROMPTS = [
  'What is the shipping policy?',
  'How do refunds work?',
  'Summarize membership benefits',
]

type ChatBubble = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  citations?: string[]
  status?: string
}

function uuid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
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
          onMeta: (response: ChatResponse) => {
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantMessage.id
                  ? {
                      ...item,
                      sources: response.sources,
                      citations: response.citations,
                      status: response.status,
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
                  <h2>Evidence-based Book Assistant</h2>
                  <p>Answers are generated only when citations are available.</p>
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
                        <div className="chat-role">{message.role === 'user' ? 'You' : 'Assistant'}</div>
                        <div className="chat-content">{message.content || (message.role === 'assistant' ? '...' : '')}</div>
                        {message.role === 'assistant' && message.sources && message.sources.length > 0 ? (
                          <div className="chat-sources">
                            <div className="chat-sources-title">Sources</div>
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
                              Insufficient evidence
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
                    placeholder="Ask a question"
                    onChange={(event) => setInput(event.target.value)}
                  />
                  <Button type="submit" disabled={isStreaming}>
                    {isStreaming ? <Spinner size="sm" /> : 'Send'}
                  </Button>
                </Form.Group>
              </Form>
            </Card.Footer>
          </Card>
        </Col>
        <Col lg={4}>
          <Card className="chat-side">
            <Card.Body>
                  <h3>Evidence Rules</h3>
                  <p>Every answer must cite documents.</p>
                  <ul>
                <li>No evidence means no answer.</li>
                <li>Open source cards to review citations.</li>
                <li>Your feedback improves the system.</li>
              </ul>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

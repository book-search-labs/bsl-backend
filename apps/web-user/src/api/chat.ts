import { createRequestContext, resolveBffBaseUrl } from './client'

export type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
}

export type ChatSource = {
  citation_key: string
  doc_id: string
  chunk_id: string
  title: string
  url: string
  snippet: string
}

export type ChatRequest = {
  version: string
  session_id?: string
  message: ChatMessage
  history?: ChatMessage[]
  options?: { stream?: boolean; top_k?: number }
}

export type ChatResponse = {
  version: string
  trace_id: string
  request_id: string
  status: string
  reason_code?: string
  recoverable?: boolean
  next_action?: string
  retry_after_ms?: number | null
  answer: ChatMessage
  sources: ChatSource[]
  citations: string[]
}

export type ChatStreamMeta = Partial<ChatResponse> & {
  risk_band?: string
}

export type ChatStreamDone = {
  status?: string
  citations?: string[]
  risk_band?: string
  reason_code?: string
  recoverable?: boolean
  next_action?: string
  retry_after_ms?: number | null
}

export type ChatStreamError = {
  code?: string
  message?: string
  next_action?: string
  retry_after_ms?: number | null
}

export type ChatFeedbackRequest = {
  version: string
  session_id: string
  message_id?: string
  rating: 'up' | 'down'
  reason_code?: string
  comment?: string
  flag_hallucination?: boolean
  flag_insufficient?: boolean
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

function parseSseChunk(buffer: string) {
  const events: Array<{ event: string; data: string }> = []
  const blocks = buffer.split('\n\n')
  const leftover = blocks.pop() ?? ''

  for (const block of blocks) {
    const lines = block.split('\n')
    let event = 'message'
    let data = ''
    for (const line of lines) {
      if (line.startsWith('event:')) {
        event = line.replace('event:', '').trim()
      } else if (line.startsWith('data:')) {
        data += line.replace('data:', '').trim()
      }
    }
    if (data) {
      events.push({ event, data })
    }
  }

  return { events, leftover }
}

export async function streamChat(
  payload: ChatRequest,
  handlers: {
    onMeta: (meta: ChatStreamMeta) => void
    onToken: (token: string) => void
    onDone?: (done: ChatStreamDone) => void
    onError?: (error: ChatStreamError) => void
  },
) {
  const baseUrl = resolveBffBaseUrl()
  const requestContext = createRequestContext()
  const url = joinUrl(baseUrl, '/chat?stream=true')

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...requestContext.headers,
    },
    body: JSON.stringify({ ...payload, trace_id: requestContext.traceId, request_id: requestContext.requestId }),
  })

  if (!response.ok || !response.body) {
    throw new Error('stream_failed')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.leftover
    for (const evt of parsed.events) {
      if (evt.event === 'meta') {
        try {
          handlers.onMeta(JSON.parse(evt.data))
        } catch {
          // ignore
        }
      } else if (evt.event === 'token' || evt.event === 'delta') {
        try {
          const payloadData = JSON.parse(evt.data)
          if (payloadData && typeof payloadData.delta === 'string') {
            handlers.onToken(payloadData.delta)
          } else {
            handlers.onToken(evt.data)
          }
        } catch {
          handlers.onToken(evt.data)
        }
      } else if (evt.event === 'done' && handlers.onDone) {
        try {
          handlers.onDone(JSON.parse(evt.data))
        } catch {
          handlers.onDone({})
        }
      } else if (evt.event === 'error' && handlers.onError) {
        try {
          handlers.onError(JSON.parse(evt.data))
        } catch {
          handlers.onError({ message: evt.data })
        }
      }
    }
  }
}

export async function submitChatFeedback(payload: ChatFeedbackRequest) {
  const baseUrl = resolveBffBaseUrl()
  const requestContext = createRequestContext()
  const url = joinUrl(baseUrl, '/chat/feedback')

  await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...requestContext.headers,
    },
    body: JSON.stringify({ ...payload, trace_id: requestContext.traceId, request_id: requestContext.requestId }),
  })
}

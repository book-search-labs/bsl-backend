type HttpErrorDetails = {
  status: number
  statusText: string
  body: unknown
}

export class HttpError extends Error {
  status: number
  statusText: string
  body: unknown

  constructor(message: string, details: HttpErrorDetails) {
    super(message)
    this.name = 'HttpError'
    this.status = details.status
    this.statusText = details.statusText
    this.body = details.body
  }
}

export type JsonInit = Omit<RequestInit, 'body'> & { body?: unknown; timeoutMs?: number }

function extractMessageFromBody(body: unknown): string | null {
  if (!body) return null
  if (typeof body === 'string') {
    const trimmed = body.trim()
    if (!trimmed) return null
    const lower = trimmed.toLowerCase()
    if (lower.startsWith('<!doctype') || lower.startsWith('<html')) {
      return null
    }
    return trimmed
  }
  if (typeof body !== 'object') return null

  const payload = body as Record<string, unknown>
  const directMessage = typeof payload.message === 'string' ? payload.message.trim() : ''
  if (directMessage) {
    return directMessage
  }

  const error = payload.error
  if (error && typeof error === 'object') {
    const errorRecord = error as Record<string, unknown>
    const nestedMessage = typeof errorRecord.message === 'string' ? errorRecord.message.trim() : ''
    if (nestedMessage) {
      return nestedMessage
    }
    const nestedCode = typeof errorRecord.code === 'string' ? errorRecord.code.trim() : ''
    if (nestedCode) {
      return nestedCode
    }
  }

  const directCode = typeof payload.code === 'string' ? payload.code.trim() : ''
  if (directCode) {
    return directCode
  }
  return null
}

function normalizeStatusText(statusText: string | null | undefined): string {
  const trimmed = (statusText ?? '').trim()
  if (!trimmed) return ''
  const lower = trimmed.toLowerCase()
  if (lower === 'http_error' || lower === 'unknown error') {
    return ''
  }
  return trimmed
}

function resolveHttpErrorMessage(parsedBody: unknown, statusText: string, status: number): string {
  const parsedMessage = extractMessageFromBody(parsedBody)
  if (parsedMessage) return parsedMessage
  const resolvedStatusText = normalizeStatusText(statusText)
  if (resolvedStatusText) return resolvedStatusText
  return `요청 처리 중 오류가 발생했습니다. (HTTP ${status})`
}

function isJsonBody(body: unknown) {
  if (body === null || body === undefined) return false
  if (typeof body === 'string') return false
  if (typeof body !== 'object') return false
  if (typeof FormData !== 'undefined' && body instanceof FormData) return false
  if (typeof Blob !== 'undefined' && body instanceof Blob) return false
  if (body instanceof ArrayBuffer) return false
  if (body instanceof URLSearchParams) return false
  if (typeof ReadableStream !== 'undefined' && body instanceof ReadableStream) return false
  return true
}

export async function fetchJson<T>(url: string, init: JsonInit = {}): Promise<T> {
  const { timeoutMs = 5000, ...requestInit } = init
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  if (requestInit.signal) {
    if (requestInit.signal.aborted) {
      controller.abort()
    } else {
      requestInit.signal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  const headers = new Headers(requestInit.headers ?? {})
  const hasJsonBody = isJsonBody(requestInit.body)
  if (hasJsonBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  const body = hasJsonBody
    ? JSON.stringify(requestInit.body)
    : (requestInit.body as BodyInit | null | undefined)

  try {
    const response = await fetch(url, {
      ...requestInit,
      signal: controller.signal,
      headers,
      body,
    })

    const text = await response.text()
    let parsed: unknown = null
    if (text) {
      try {
        parsed = JSON.parse(text)
      } catch {
        parsed = text
      }
    }

    if (!response.ok) {
      const rawStatusText = normalizeStatusText(response.statusText)
      throw new HttpError(resolveHttpErrorMessage(parsed, rawStatusText, response.status), {
        status: response.status,
        statusText: rawStatusText || 'http_error',
        body: parsed,
      })
    }

    return parsed as T
  } catch (error) {
    if (error instanceof HttpError) {
      throw error
    }

    const message = error instanceof Error ? error.message : String(error)
    const statusText = error instanceof Error && error.name === 'AbortError' ? 'timeout' : 'network_error'
    const fallbackMessage =
      statusText === 'timeout'
        ? '요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.'
        : '네트워크 연결 오류가 발생했습니다. 연결 상태를 확인해주세요.'

    const userMessage = statusText === 'network_error' || statusText === 'timeout' ? fallbackMessage : message
    throw new HttpError(userMessage || fallbackMessage, {
      status: 0,
      statusText,
      body: message || fallbackMessage,
    })
  } finally {
    clearTimeout(timeoutId)
  }
}

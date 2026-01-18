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

type JsonInit = RequestInit & { timeoutMs?: number }

function isJsonBody(body: BodyInit | null | undefined) {
  if (!body) return false
  if (typeof body === 'string') return false
  if (body instanceof FormData) return false
  if (body instanceof Blob) return false
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
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  const body = isJsonBody(requestInit.body) ? JSON.stringify(requestInit.body) : requestInit.body

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
      throw new HttpError(response.statusText || 'http_error', {
        status: response.status,
        statusText: response.statusText || 'http_error',
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

    throw new HttpError(message || statusText, {
      status: 0,
      statusText,
      body: message,
    })
  } finally {
    clearTimeout(timeoutId)
  }
}

export type FetchSuccess<T> = { ok: true; status: number; data: T }

type FetchJsonOptions = RequestInit & { timeoutMs?: number }

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

export async function fetchJson<T>(url: string, options: FetchJsonOptions = {}): Promise<FetchSuccess<T>> {
  const { timeoutMs = 5000, ...init } = options
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  if (init.signal) {
    if (init.signal.aborted) {
      controller.abort()
    } else {
      init.signal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(init.headers ?? {}),
      },
    })

    const text = await response.text()
    let body: unknown = null
    if (text) {
      try {
        body = JSON.parse(text)
      } catch {
        body = text
      }
    }

    if (!response.ok) {
      throw new HttpError(response.statusText || 'http_error', {
        status: response.status,
        statusText: response.statusText || 'http_error',
        body,
      })
    }

    return { ok: true, status: response.status, data: body as T }
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

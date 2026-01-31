import { HttpError } from './http'

type ApiMode = 'bff_primary' | 'direct_primary' | 'bff_only' | 'direct_only'

type ApiTarget = 'bff' | 'direct'

type RouteConfig<T> = {
  route: string
  mode?: ApiMode
  allowFallback?: boolean
  requestContext?: ApiRequestContext
  shouldFallback?: (error: unknown) => boolean
  bff?: (context: ApiRequestContext) => Promise<T>
  direct?: (context: ApiRequestContext) => Promise<T>
}

export type ApiRequestContext = {
  requestId: string
  traceId: string
  traceparent: string
  headers: Record<string, string>
}

const DEFAULT_MODE: ApiMode = 'bff_primary'

export function resolveApiMode(): ApiMode {
  const raw = (import.meta.env.VITE_API_MODE ?? DEFAULT_MODE).toLowerCase()
  if (raw === 'bff_primary' || raw === 'direct_primary' || raw === 'bff_only' || raw === 'direct_only') {
    return raw
  }
  return DEFAULT_MODE
}

export function resolveBffBaseUrl() {
  return import.meta.env.VITE_BFF_BASE_URL ?? 'http://localhost:8088'
}

export function resolveCommerceBaseUrl() {
  return import.meta.env.VITE_COMMERCE_BASE_URL ?? 'http://localhost:8091'
}

function resolveUserId() {
  return (
    localStorage.getItem('bsl.userId') ??
    (import.meta.env.VITE_USER_ID as string | undefined) ??
    '1'
  )
}

function randomHex(bytes: number) {
  if (typeof crypto !== 'undefined' && 'getRandomValues' in crypto) {
    const data = new Uint8Array(bytes)
    crypto.getRandomValues(data)
    return Array.from(data)
      .map((value) => value.toString(16).padStart(2, '0'))
      .join('')
  }
  return Array.from({ length: bytes }, () => Math.floor(Math.random() * 256))
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('')
}

export function createRequestContext(): ApiRequestContext {
  const traceId = randomHex(16)
  const spanId = randomHex(8)
  const requestId = `${traceId}-${spanId}`
  const traceparent = `00-${traceId}-${spanId}-01`
  const userId = resolveUserId()
  return {
    requestId,
    traceId,
    traceparent,
    headers: {
      'x-request-id': requestId,
      'x-trace-id': traceId,
      traceparent,
      'x-user-id': userId,
    },
  }
}

function shouldFallback(error: unknown) {
  return error instanceof HttpError && (error.status === 0 || error.status >= 500)
}

export async function routeRequest<T>(config: RouteConfig<T>): Promise<T> {
  const mode = config.mode ?? resolveApiMode()
  const allowFallback = config.allowFallback ?? true
  const requestContext = config.requestContext ?? createRequestContext()
  const primary: ApiTarget = mode === 'direct_primary' || mode === 'direct_only' ? 'direct' : 'bff'
  const secondary: ApiTarget = primary === 'bff' ? 'direct' : 'bff'
  const primaryCall = primary === 'bff' ? config.bff : config.direct
  const secondaryCall = secondary === 'bff' ? config.bff : config.direct

  if (!primaryCall) {
    throw new Error(`Missing ${primary} handler for ${config.route}`)
  }

  try {
    const result = await primaryCall(requestContext)
    console.info(`[api] ${config.route} via ${primary} mode=${mode} request_id=${requestContext.requestId}`)
    return result
  } catch (error) {
    const allow =
      allowFallback &&
      (mode === 'bff_primary' || mode === 'direct_primary') &&
      secondaryCall &&
      (config.shouldFallback ? config.shouldFallback(error) : shouldFallback(error))

    if (allow && secondaryCall) {
      console.warn(
        `[api] ${config.route} fallback to ${secondary} mode=${mode} request_id=${requestContext.requestId}`,
      )
      return secondaryCall(requestContext)
    }

    throw error
  }
}

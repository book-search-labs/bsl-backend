import type { FetchResult } from './api'

export type AdminApiMode = 'bff_primary' | 'bff_only'
export type ApiTarget = 'bff' | 'direct'

export type ApiRequestContext = {
  requestId: string
  traceId: string
  traceparent: string
  headers: Record<string, string>
}

type RouteConfig<T> = {
  route: string
  mode?: AdminApiMode
  allowFallback?: boolean
  requestContext?: ApiRequestContext
  bff: (context: ApiRequestContext) => Promise<FetchResult<T>>
  direct: (context: ApiRequestContext) => Promise<FetchResult<T>>
}

const DEFAULT_MODE: AdminApiMode = 'bff_primary'

export function resolveAdminApiMode(): AdminApiMode {
  const raw = (import.meta.env.VITE_ADMIN_API_MODE ?? DEFAULT_MODE).toLowerCase()
  if (raw === 'bff_primary' || raw === 'bff_only') {
    return raw
  }
  return DEFAULT_MODE
}

export function resolveBffBaseUrl() {
  return import.meta.env.VITE_BFF_BASE_URL ?? 'http://localhost:8088'
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
  return {
    requestId,
    traceId,
    traceparent,
    headers: {
      'x-request-id': requestId,
      'x-trace-id': traceId,
      traceparent,
    },
  }
}

function shouldFallback<T>(result: FetchResult<T>) {
  return !result.ok && (result.status === 0 || result.status >= 500)
}

export async function routeRequest<T>(config: RouteConfig<T>): Promise<{
  result: FetchResult<T>
  target: ApiTarget
  requestId: string
}> {
  const mode = config.mode ?? resolveAdminApiMode()
  const allowFallback = config.allowFallback ?? false
  const requestContext = config.requestContext ?? createRequestContext()

  const primary: ApiTarget = 'bff'
  const secondary: ApiTarget = 'direct'

  const primaryResult = await config.bff(requestContext)
  if (primaryResult.ok) {
    console.info(`[admin-api] ${config.route} via ${primary} mode=${mode} request_id=${requestContext.requestId}`)
    return { result: primaryResult, target: primary, requestId: requestContext.requestId }
  }

  const canFallback = allowFallback && mode === 'bff_primary' && shouldFallback(primaryResult)
  if (canFallback) {
    console.warn(`[admin-api] ${config.route} fallback to ${secondary} request_id=${requestContext.requestId}`)
    const fallbackResult = await config.direct(requestContext)
    return { result: fallbackResult, target: secondary, requestId: requestContext.requestId }
  }

  return { result: primaryResult, target: primary, requestId: requestContext.requestId }
}

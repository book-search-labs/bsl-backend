import { createRequestContext, resolveApiMode, resolveBffBaseUrl, routeRequest } from './client'
import { fetchJson } from './http'

export type AutocompleteSuggestion = {
  text: string
  score?: number
  source?: string
  suggest_id?: string
  type?: string
  target_id?: string
  target_doc_id?: string
  [key: string]: unknown
}

export type AutocompleteResponse = {
  version?: string
  trace_id?: string
  request_id?: string
  took_ms?: number
  suggestions?: AutocompleteSuggestion[]
  [key: string]: unknown
}

export type AutocompleteSelectRequest = {
  q?: string
  text: string
  suggest_id?: string
  type?: string
  position?: number
  source?: string
  target_id?: string
  target_doc_id?: string
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

function resolveAutocompleteBaseUrl() {
  return (
    import.meta.env.VITE_AUTOCOMPLETE_SERVICE_BASE_URL ??
    import.meta.env.VITE_AUTOCOMPLETE_BASE_URL ??
    'http://localhost:8081'
  )
}

export async function fetchAutocomplete(
  query: string,
  size: number,
  signal?: AbortSignal,
): Promise<AutocompleteResponse> {
  const params = new URLSearchParams({ q: query, size: String(size) })
  const requestContext = createRequestContext()

  const bffCall = (context: typeof requestContext) => {
    const baseUrl = resolveBffBaseUrl()
    const url = joinUrl(baseUrl, `/autocomplete?${params.toString()}`)
    return fetchJson<AutocompleteResponse>(url, { method: 'GET', signal, headers: context.headers })
  }

  const directCall = (context: typeof requestContext) => {
    const baseUrl = resolveAutocompleteBaseUrl()
    const url = joinUrl(baseUrl, `/autocomplete?${params.toString()}`)
    return fetchJson<AutocompleteResponse>(url, { method: 'GET', signal, headers: context.headers })
  }

  return routeRequest({
    route: 'autocomplete',
    mode: resolveApiMode(),
    requestContext,
    bff: bffCall,
    direct: directCall,
    shouldFallback: () => !(signal && signal.aborted),
  })
}

export async function postAutocompleteSelect(payload: AutocompleteSelectRequest): Promise<void> {
  const mode = resolveApiMode()
  if (mode === 'direct_only') {
    return
  }
  const requestContext = createRequestContext()
  const baseUrl = resolveBffBaseUrl()
  const url = joinUrl(baseUrl, '/autocomplete/select')
  try {
    await fetchJson(url, {
      method: 'POST',
      headers: requestContext.headers,
      body: payload,
    })
  } catch (error) {
    console.warn('[api] autocomplete select failed', error)
  }
}

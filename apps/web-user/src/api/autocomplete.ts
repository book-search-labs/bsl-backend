import { createRequestContext, resolveApiMode, resolveBffBaseUrl, routeRequest } from './client'
import { fetchJson } from './http'

export type AutocompleteSuggestion = {
  text: string
  score?: number
  source?: string
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

import { fetchJson } from './http'

export type AutocompleteSuggestion = {
  text: string
  score?: number
  source?: string
  [key: string]: unknown
}

export type AutocompleteResponse = {
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
  const baseUrl = resolveAutocompleteBaseUrl()
  const params = new URLSearchParams({ q: query, size: String(size) })
  const url = joinUrl(baseUrl, `/autocomplete?${params.toString()}`)

  return fetchJson<AutocompleteResponse>(url, { method: 'GET', signal })
}

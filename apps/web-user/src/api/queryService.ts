import { fetchJson } from './http'

type QueryContextPayload = {
  query: { raw: string }
  client: { device: string }
  user: null
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

export async function postQueryContext(rawQuery: string, headers?: HeadersInit): Promise<unknown> {
  const queryBaseUrl = import.meta.env.VITE_QUERY_BASE_URL ?? 'http://localhost:8001'
  const payload: QueryContextPayload = {
    query: { raw: rawQuery },
    client: { device: 'web_user' },
    user: null,
  }

  return fetchJson(joinUrl(queryBaseUrl, '/query-context'), {
    method: 'POST',
    headers,
    body: payload,
  })
}

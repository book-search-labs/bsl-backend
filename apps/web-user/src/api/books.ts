import { createRequestContext, resolveApiMode, resolveBffBaseUrl, routeRequest } from './client'
import { fetchJson } from './http'
import { getBookByDocId, type BookDetailResponse } from './searchService'

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

export async function getBookDetail(docId: string): Promise<BookDetailResponse> {
  const requestContext = createRequestContext()
  const encodedId = encodeURIComponent(docId)

  return routeRequest<BookDetailResponse>({
    route: 'book_detail',
    mode: resolveApiMode(),
    requestContext,
    bff: (context) =>
      fetchJson<BookDetailResponse>(joinUrl(resolveBffBaseUrl(), `/books/${encodedId}`), {
        method: 'GET',
        headers: context.headers,
      }),
    direct: (context) => getBookByDocId(docId, context.headers),
  })
}

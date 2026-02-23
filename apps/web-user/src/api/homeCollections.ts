import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type HomeCollectionItem = {
  doc_id?: string
  title_ko?: string
  authors?: string[]
  publisher_name?: string
  issued_year?: number
  edition_labels?: string[]
}

export type HomeCollectionSection = {
  key: 'bestseller' | 'new' | 'editor' | string
  title: string
  note?: string
  link?: string
  items: HomeCollectionItem[]
}

type HomeCollectionsResponse = {
  sections?: HomeCollectionSection[]
  limit_per_section?: number
}

export type HomeCollectionsResult = {
  sections: HomeCollectionSection[]
  limitPerSection: number
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

async function callApi<T>(path: string, init?: JsonInit) {
  const requestContext = createRequestContext()
  return routeRequest<T>({
    route: path,
    mode: resolveApiMode(),
    requestContext,
    bff: (context) => fetchJson<T>(joinUrl(resolveBffBaseUrl(), path), { ...init, headers: context.headers }),
    direct: (context) => fetchJson<T>(joinUrl(resolveCommerceBaseUrl(), path), { ...init, headers: context.headers }),
  })
}

export async function fetchHomeCollections(limitPerSection = 8): Promise<HomeCollectionsResult> {
  const params = new URLSearchParams()
  params.set('limit_per_section', String(limitPerSection))

  const response = await callApi<HomeCollectionsResponse>(`/api/v1/home/collections?${params.toString()}`, {
    method: 'GET',
  })

  return {
    sections: Array.isArray(response.sections) ? response.sections : [],
    limitPerSection: typeof response.limit_per_section === 'number' ? response.limit_per_section : limitPerSection,
  }
}

import { createRequestContext, resolveBffBaseUrl } from './client'
import { fetchJson } from './http'

export type KdcCategoryNode = {
  id: number
  code: string
  name: string
  depth: number
  children?: KdcCategoryNode[]
}

type KdcCategoryResponse = {
  version?: string
  trace_id?: string
  request_id?: string
  categories?: KdcCategoryNode[]
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

export async function fetchKdcCategories(): Promise<KdcCategoryNode[]> {
  const requestContext = createRequestContext()
  const response = await fetchJson<KdcCategoryResponse>(joinUrl(resolveBffBaseUrl(), '/categories/kdc'), {
    method: 'GET',
    headers: requestContext.headers,
  })
  return Array.isArray(response?.categories) ? response.categories : []
}

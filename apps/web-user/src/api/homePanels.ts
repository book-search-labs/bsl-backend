import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type HomePanelType = 'EVENT' | 'NOTICE'

export type HomePanelItem = {
  item_id: number
  type: HomePanelType
  badge?: string | null
  title: string
  subtitle?: string | null
  summary?: string | null
  detail_body?: string | null
  link_url?: string | null
  cta_label?: string | null
  banner_image_url?: string | null
  starts_at?: string | null
  ends_at?: string | null
  sort_order?: number | null
}

type HomePanelsResponse = {
  items?: HomePanelItem[]
  count?: number
  total_count?: number
  limit?: number
  type?: HomePanelType | null
}

type HomePanelDetailResponse = {
  item?: HomePanelItem
}

export type HomePanelsResult = {
  items: HomePanelItem[]
  count: number
  totalCount: number
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

export async function fetchHomePanels(limit = 31, type?: HomePanelType): Promise<HomePanelsResult> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (type) {
    params.set('type', type)
  }

  const response = await callApi<HomePanelsResponse>(`/api/v1/home/panels?${params.toString()}`, { method: 'GET' })
  const items = Array.isArray(response.items) ? response.items : []
  const count = typeof response.count === 'number' ? response.count : items.length
  const totalCount = typeof response.total_count === 'number' ? response.total_count : count
  return {
    items,
    count,
    totalCount,
  }
}

export async function fetchHomePanelDetail(itemId: number): Promise<HomePanelItem> {
  const response = await callApi<HomePanelDetailResponse>(`/api/v1/home/panels/${itemId}`, { method: 'GET' })
  if (!response.item) {
    throw new Error('이벤트/공지 정보를 찾을 수 없습니다.')
  }
  return response.item
}

import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type HomeBenefitItem = {
  item_id: number
  benefit_code?: string | null
  badge?: string | null
  title: string
  description?: string | null
  discount_type?: string | null
  discount_value?: number | null
  discount_label?: string | null
  min_order_amount?: number | null
  min_order_amount_label?: string | null
  max_discount_amount?: number | null
  max_discount_amount_label?: string | null
  valid_from?: string | null
  valid_to?: string | null
  daily_limit?: number | null
  remaining_daily?: number | null
  link_url?: string | null
  cta_label?: string | null
}

type HomeBenefitsResponse = {
  today?: string
  items?: HomeBenefitItem[]
  count?: number
  total_count?: number
  limit?: number
}

export type HomeBenefitsResult = {
  today: string | null
  items: HomeBenefitItem[]
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

export async function fetchHomeBenefits(limit = 12): Promise<HomeBenefitsResult> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))

  const response = await callApi<HomeBenefitsResponse>(`/api/v1/home/benefits?${params.toString()}`, { method: 'GET' })
  const items = Array.isArray(response.items) ? response.items : []
  const count = typeof response.count === 'number' ? response.count : items.length
  const totalCount = typeof response.total_count === 'number' ? response.total_count : count

  return {
    today: typeof response.today === 'string' ? response.today : null,
    items,
    count,
    totalCount,
  }
}

import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type CurrentOffer = {
  offer_id: number
  sku_id: number
  seller_id: number
  currency: string
  list_price: number
  sale_price: number
  effective_price: number
  available_qty?: number | null
  is_in_stock?: boolean | null
  shipping_policy_json?: string | null
  purchase_limit_json?: string | null
}

type CurrentOfferResponse = {
  current_offer: CurrentOffer
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

export async function getCurrentOfferByMaterial(materialId: string) {
  const encoded = encodeURIComponent(materialId)
  const response = await callApi<CurrentOfferResponse>(`/api/v1/materials/${encoded}/current-offer`, {
    method: 'GET',
  })
  return response.current_offer
}

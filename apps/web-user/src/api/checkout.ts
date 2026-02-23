import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'
import type { CartBenefits, CartItem, CartLoyalty } from './cart'

export type Address = {
  address_id: number
  name: string
  phone: string
  zip?: string | null
  addr1?: string | null
  addr2?: string | null
  is_default?: number | boolean
}

export type CheckoutSummary = {
  cart: {
    cart_id: number
    items: CartItem[]
    totals: {
      subtotal: number
      shipping_fee: number
      discount: number
      total: number
    }
    benefits?: CartBenefits
    loyalty?: CartLoyalty
  } | null
  addresses: Address[]
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

export async function fetchCheckoutSummary() {
  const response = await callApi<{ cart: CheckoutSummary['cart']; addresses: Address[] }>('/api/v1/checkout', {
    method: 'GET',
  })
  return response
}

export async function createAddress(payload: {
  name: string
  phone: string
  zip?: string
  addr1?: string
  addr2?: string
  isDefault?: boolean
}) {
  const response = await callApi<{ address: Address }>('/api/v1/addresses', {
    method: 'POST',
    body: payload,
  })
  return response.address
}

export async function setDefaultAddress(addressId: number) {
  const response = await callApi<{ address: Address }>(`/api/v1/addresses/${addressId}/default`, {
    method: 'POST',
  })
  return response.address
}

export async function listAddresses() {
  const response = await callApi<{ items: Address[] }>('/api/v1/addresses', { method: 'GET' })
  return response.items ?? []
}

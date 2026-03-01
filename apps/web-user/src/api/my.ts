import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'
import type {
  CouponItem,
  ELibraryBook,
  MyComment,
  MyGiftItem,
  MyInquiry,
  MyNotification,
  NotificationCategory,
  NotificationPreference,
  VoucherItem,
  WalletPointLog,
  WishlistItem,
} from '../types/my'

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

export async function fetchWishlistItems() {
  const response = await callApi<{ items: WishlistItem[] }>('/api/v1/my/wishlist', { method: 'GET' })
  return response.items ?? []
}

export async function createWishlistItem(payload: {
  docId: string
  title: string
  author: string
  coverUrl: string | null
  price: number
}) {
  const response = await callApi<{ item: WishlistItem }>('/api/v1/my/wishlist', {
    method: 'POST',
    body: payload,
  })
  return response.item
}

export async function deleteWishlistItem(docId: string) {
  const response = await callApi<{ items: WishlistItem[] }>(`/api/v1/my/wishlist/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
  })
  return response.items ?? []
}

export async function fetchELibraryBooks() {
  const response = await callApi<{ items: ELibraryBook[] }>('/api/v1/my/elib', { method: 'GET' })
  return response.items ?? []
}

export async function fetchPointLogs() {
  const response = await callApi<{ balance: number; items: WalletPointLog[] }>('/api/v1/my/wallet/points', {
    method: 'GET',
  })
  return response
}

export async function fetchVouchers() {
  const response = await callApi<{ items: VoucherItem[] }>('/api/v1/my/wallet/vouchers', { method: 'GET' })
  return response.items ?? []
}

export async function fetchCoupons() {
  const response = await callApi<{ items: CouponItem[] }>('/api/v1/my/wallet/coupons', { method: 'GET' })
  return response.items ?? []
}

export async function fetchComments() {
  const response = await callApi<{ items: MyComment[] }>('/api/v1/my/comments', { method: 'GET' })
  return response.items ?? []
}

export async function createComment(payload: {
  orderId: number
  title: string
  rating: number
  content: string
}) {
  const response = await callApi<{ item: MyComment }>('/api/v1/my/comments', {
    method: 'POST',
    body: payload,
  })
  return response.item
}

export async function fetchInquiries() {
  const response = await callApi<{ items: MyInquiry[] }>('/api/v1/my/inquiries', { method: 'GET' })
  return response.items ?? []
}

export async function createInquiry(payload: Pick<MyInquiry, 'title' | 'category' | 'content'>) {
  const response = await callApi<{ item: MyInquiry }>('/api/v1/my/inquiries', {
    method: 'POST',
    body: payload,
  })
  return response.item
}

export async function fetchNotifications(filter: NotificationCategory | 'all' = 'all', unreadOnly = false) {
  const params = new URLSearchParams()
  if (filter !== 'all') {
    params.set('category', filter)
  }
  if (unreadOnly) {
    params.set('unreadOnly', 'true')
  }
  const query = params.toString()
  const response = await callApi<{ items: MyNotification[]; unread_count?: number }>(
    `/api/v1/my/notifications${query ? `?${query}` : ''}`,
    { method: 'GET' },
  )
  return {
    items: response.items ?? [],
    unreadCount: response.unread_count ?? (response.items ?? []).filter((item) => !item.read).length,
  }
}

export async function fetchNotificationPreferences() {
  const response = await callApi<{ items: NotificationPreference[] }>('/api/v1/my/notification-preferences', {
    method: 'GET',
  })
  return response.items ?? []
}

export async function updateNotificationPreference(category: NotificationCategory, enabled: boolean) {
  const response = await callApi<{ items: NotificationPreference[] }>(
    `/api/v1/my/notification-preferences/${encodeURIComponent(category)}`,
    {
      method: 'POST',
      body: { enabled },
    },
  )
  return response.items ?? []
}

export async function readNotification(notificationId: string) {
  await callApi(`/api/v1/my/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: 'POST',
  })
}

export async function readAllNotifications() {
  await callApi('/api/v1/my/notifications/read-all', {
    method: 'POST',
  })
}

export async function fetchGiftItems() {
  const response = await callApi<{ items: MyGiftItem[] }>('/api/v1/my/gifts', { method: 'GET' })
  return response.items ?? []
}

export async function fetchGiftItemById(giftId: string) {
  const response = await callApi<{ item: MyGiftItem }>(`/api/v1/my/gifts/${encodeURIComponent(giftId)}`, {
    method: 'GET',
  })
  return response.item ?? null
}

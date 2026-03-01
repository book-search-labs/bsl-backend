import {
  createComment,
  createInquiry as createInquiryApi,
  createWishlistItem,
  deleteWishlistItem,
  fetchComments,
  fetchCoupons,
  fetchELibraryBooks,
  fetchGiftItemById,
  fetchGiftItems,
  fetchInquiries,
  fetchNotificationPreferences,
  fetchNotifications,
  fetchPointLogs,
  fetchVouchers,
  fetchWishlistItems,
  readAllNotifications,
  readNotification,
  updateNotificationPreference,
} from '../api/my'
import type { NotificationCategory } from '../types/my'

let cachedUnreadNotificationCount = 0

export async function listWishlistItems() {
  return fetchWishlistItems()
}

export async function isWishlistItem(docId: string) {
  const items = await fetchWishlistItems()
  return items.some((item) => item.docId === docId)
}

export async function addWishlistItem(payload: {
  docId: string
  title: string
  author: string
  coverUrl: string | null
  price: number
}) {
  return createWishlistItem(payload)
}

export async function removeWishlistItem(docId: string) {
  return deleteWishlistItem(docId)
}

export async function listELibraryBooks() {
  return fetchELibraryBooks()
}

export async function listPointLogs() {
  const response = await fetchPointLogs()
  return response.items
}

export async function listVouchers() {
  return fetchVouchers()
}

export async function listCoupons() {
  return fetchCoupons()
}

export async function listComments() {
  return fetchComments()
}

export async function addComment(payload: { orderId: number; title: string; rating: number; content: string }) {
  return createComment(payload)
}

export async function listInquiries() {
  return fetchInquiries()
}

export async function createInquiry(payload: { title: string; category: string; content: string }) {
  return createInquiryApi(payload)
}

export async function listNotifications(filter: NotificationCategory | 'all' = 'all', unreadOnly = false) {
  const response = await fetchNotifications(filter, unreadOnly)
  cachedUnreadNotificationCount = response.unreadCount
  return response.items
}

export async function listNotificationPreferences() {
  return fetchNotificationPreferences()
}

export async function setNotificationPreference(category: NotificationCategory, enabled: boolean) {
  return updateNotificationPreference(category, enabled)
}

export async function markNotificationRead(id: string) {
  await readNotification(id)
}

export async function markAllNotificationsRead() {
  await readAllNotifications()
}

export function getUnreadNotificationCountSync() {
  return cachedUnreadNotificationCount
}

export async function listGiftItems() {
  return fetchGiftItems()
}

export async function getGiftItemById(giftId: string) {
  return fetchGiftItemById(giftId)
}

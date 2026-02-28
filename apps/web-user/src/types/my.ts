export type MyMenuItem = {
  key: string
  label: string
  to: string
  hidden?: boolean
}

export type MyMenuGroup = {
  key: string
  title: string
  items: MyMenuItem[]
}

export type NotificationCategory = 'order' | 'event' | 'benefit' | 'system'

export type MyNotification = {
  id: string
  category: NotificationCategory
  title: string
  body: string
  createdAt: string
  read: boolean
}

export type NotificationPreference = {
  category: NotificationCategory
  label: string
  enabled: boolean
}

export type MyInquiry = {
  id: string
  title: string
  category: string
  content: string
  status: '접수' | '처리 중' | '답변 완료'
  createdAt: string
}

export type MyComment = {
  id: string
  orderId: number
  title: string
  rating: number
  content: string
  createdAt: string
}

export type WalletPointLog = {
  id: string
  description: string
  amount: number
  createdAt: string
}

export type VoucherItem = {
  id: string
  name: string
  value: number
  expiresAt: string
  used: boolean
}

export type CouponItem = {
  id: string
  name: string
  discountLabel: string
  expiresAt: string
  usable: boolean
}

export type WishlistItem = {
  id: string
  docId: string
  title: string
  author: string
  coverUrl: string | null
  price: number
}

export type ELibraryBook = {
  id: string
  title: string
  author: string
  publisher: string
  downloadedAt: string
  drmPolicy: string
  coverUrl: string | null
}

export type GiftDirection = 'SENT' | 'RECEIVED'

export type MyGiftBook = {
  docId: string
  title: string
  author: string
  publisher: string
  quantity: number
  unitPrice: number
  coverUrl: string | null
}

export type MyGiftItem = {
  id: string
  title: string
  status: string
  createdAt: string
  direction: GiftDirection
  partnerName: string
  message: string
  giftCode?: string
  expiresAt?: string
  items: MyGiftBook[]
}

export type MySessionUser = {
  userId: number
  name: string
  email: string
  membershipLabel: string
  phone: string
}

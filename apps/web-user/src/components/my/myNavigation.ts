import type { MyMenuGroup, MyMenuItem } from '../../types/my'

export const MY_MENU_GROUPS: MyMenuGroup[] = [
  {
    key: 'shopping',
    title: '쇼핑내역',
    items: [
      { key: 'orders', label: '주문/배송 목록', to: '/my/orders' },
      { key: 'gifts', label: '선물함', to: '/my/gifts' },
      { key: 'store-purchases', label: '매장 구매 내역', to: '/my/store-purchases', hidden: true },
      { key: 'receipts', label: '영수증 조회/후적립', to: '/my/receipts', hidden: true },
    ],
  },
  {
    key: 'library',
    title: '라이브러리',
    items: [
      { key: 'wishlist', label: '찜(위시리스트)', to: '/my/wishlist' },
      { key: 'comments', label: '코멘트', to: '/my/comments' },
      { key: 'elib', label: 'e-라이브러리', to: '/my/elib' },
    ],
  },
  {
    key: 'wallet',
    title: '나의 통장',
    items: [
      { key: 'points', label: '통합포인트', to: '/my/wallet/points' },
      { key: 'vouchers', label: 'e교환권', to: '/my/wallet/vouchers' },
      { key: 'coupons', label: '쿠폰', to: '/my/wallet/coupons' },
    ],
  },
  {
    key: 'support',
    title: '문의내역',
    items: [{ key: 'inquiries', label: '1:1 문의', to: '/my/support/inquiries' }],
  },
  {
    key: 'settings',
    title: '회원정보/설정',
    items: [
      { key: 'profile', label: '회원정보 수정', to: '/my/profile' },
      { key: 'addresses', label: '배송 주소록', to: '/my/addresses' },
      { key: 'notifications', label: '알림함', to: '/my/notifications' },
    ],
  },
]

export const MY_DROPDOWN_LINKS: MyMenuItem[] = [
  { key: 'my-home', label: '마이페이지', to: '/my' },
  { key: 'my-orders', label: '주문·배송', to: '/my/orders' },
  { key: 'my-wishlist', label: '찜', to: '/my/wishlist' },
  { key: 'my-gifts', label: '선물함', to: '/my/gifts' },
  { key: 'my-notifications', label: '알림함', to: '/my/notifications' },
  { key: 'my-settings', label: '설정', to: '/my/profile' },
]

export function flattenMyMenuItems() {
  return MY_MENU_GROUPS.flatMap((group) => group.items.filter((item) => !item.hidden))
}

export function findMyMenuItem(pathname: string) {
  const target = flattenMyMenuItems().find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))
  if (target) {
    return target
  }

  if (pathname === '/my' || pathname.startsWith('/my/')) {
    return {
      key: 'my-home',
      label: '마이페이지',
      to: '/my',
    }
  }

  return null
}

import { Route, Routes } from 'react-router-dom'

import AppShell from '../layouts/AppShell'
import AboutPage from '../pages/AboutPage'
import BookDetailPage from '../pages/BookDetailPage'
import ChatPage from '../pages/ChatPage'
import EventDetailPage from '../pages/EventDetailPage'
import EventsPage from '../pages/EventsPage'
import BenefitsPage from '../pages/BenefitsPage'
import HomePage from '../pages/HomePage'
import NotFoundPage from '../pages/NotFoundPage'
import PreordersPage from '../pages/PreordersPage'
import SearchPage from '../pages/SearchPage'
import CartPage from '../pages/cart/CartPage'
import CheckoutPage from '../pages/checkout/CheckoutPage'
import PaymentProcessingPage from '../pages/payment/PaymentProcessingPage'
import PaymentResultPage from '../pages/payment/PaymentResultPage'
import OrderListPage from '../pages/orders/OrderListPage'
import OrderDetailPage from '../pages/orders/OrderDetailPage'
import RefundRequestPage from '../pages/refund/RefundRequestPage'
import MyLayout from '../components/my/MyLayout'
import MyAddressesPage from '../pages/my/MyAddressesPage'
import MyCommentsPage from '../pages/my/MyCommentsPage'
import MyCouponsPage from '../pages/my/MyCouponsPage'
import MyDashboardPage from '../pages/my/MyDashboardPage'
import MyELibraryPage from '../pages/my/MyELibraryPage'
import MyGiftDetailPage from '../pages/my/MyGiftDetailPage'
import MyGiftsPage from '../pages/my/MyGiftsPage'
import MyInquiriesPage from '../pages/my/MyInquiriesPage'
import MyNotificationsPage from '../pages/my/MyNotificationsPage'
import MyOrdersPage from '../pages/my/MyOrdersPage'
import MyPointsPage from '../pages/my/MyPointsPage'
import MyProfilePage from '../pages/my/MyProfilePage'
import MyVouchersPage from '../pages/my/MyVouchersPage'
import MyWishlistPage from '../pages/my/MyWishlistPage'

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="events/:itemId" element={<EventDetailPage />} />
        <Route path="benefits" element={<BenefitsPage />} />
        <Route path="preorders" element={<PreordersPage />} />
        <Route path="book/:docId" element={<BookDetailPage />} />
        <Route path="cart" element={<CartPage />} />
        <Route path="checkout" element={<CheckoutPage />} />
        <Route path="payment">
          <Route path="process/:orderId" element={<PaymentProcessingPage />} />
          <Route path="result/:paymentId" element={<PaymentResultPage />} />
        </Route>
        <Route path="orders" element={<OrderListPage />} />
        <Route path="orders/:orderId" element={<OrderDetailPage />} />
        <Route path="orders/:orderId/refund" element={<RefundRequestPage />} />
        <Route path="my" element={<MyLayout />}>
          <Route index element={<MyDashboardPage />} />
          <Route path="orders" element={<MyOrdersPage />} />
          <Route path="gifts" element={<MyGiftsPage />} />
          <Route path="gifts/:giftId" element={<MyGiftDetailPage />} />
          <Route path="wishlist" element={<MyWishlistPage />} />
          <Route path="comments" element={<MyCommentsPage />} />
          <Route path="elib" element={<MyELibraryPage />} />
          <Route path="wallet">
            <Route path="points" element={<MyPointsPage />} />
            <Route path="vouchers" element={<MyVouchersPage />} />
            <Route path="coupons" element={<MyCouponsPage />} />
          </Route>
          <Route path="support">
            <Route path="inquiries" element={<MyInquiriesPage />} />
          </Route>
          <Route path="profile" element={<MyProfilePage />} />
          <Route path="addresses" element={<MyAddressesPage />} />
          <Route path="notifications" element={<MyNotificationsPage />} />
        </Route>
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

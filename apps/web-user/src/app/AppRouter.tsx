import { Route, Routes } from 'react-router-dom'

import AppShell from '../layouts/AppShell'
import AboutPage from '../pages/AboutPage'
import BookDetailPage from '../pages/BookDetailPage'
import ChatPage from '../pages/ChatPage'
import HomePage from '../pages/HomePage'
import NotFoundPage from '../pages/NotFoundPage'
import SearchPage from '../pages/SearchPage'
import CartPage from '../pages/cart/CartPage'
import CheckoutPage from '../pages/checkout/CheckoutPage'
import PaymentProcessingPage from '../pages/payment/PaymentProcessingPage'
import PaymentResultPage from '../pages/payment/PaymentResultPage'
import OrderListPage from '../pages/orders/OrderListPage'
import OrderDetailPage from '../pages/orders/OrderDetailPage'
import RefundRequestPage from '../pages/refund/RefundRequestPage'

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="chat" element={<ChatPage />} />
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
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

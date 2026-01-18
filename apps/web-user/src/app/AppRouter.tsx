import { Route, Routes } from 'react-router-dom'

import AppShell from '../layouts/AppShell'
import AboutPage from '../pages/AboutPage'
import BookDetailPage from '../pages/BookDetailPage'
import HomePage from '../pages/HomePage'
import NotFoundPage from '../pages/NotFoundPage'
import SearchPage from '../pages/SearchPage'

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="book/:docId" element={<BookDetailPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

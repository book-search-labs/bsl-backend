import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { getSessionId } from '../services/mySession'

export default function RequireAuth() {
  const location = useLocation()
  const sessionId = getSessionId()
  if (sessionId) {
    return <Outlet />
  }

  const redirect = `${location.pathname}${location.search}`
  return <Navigate to={`/login?redirect=${encodeURIComponent(redirect)}`} replace />
}

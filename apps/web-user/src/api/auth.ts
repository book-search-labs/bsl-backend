import { createRequestContext, resolveBffBaseUrl } from './client'
import { fetchJson } from './http'
import type { MySessionUser } from '../types/my'

type AuthSessionPayload = {
  session_id: string
  expires_at: string
  user: {
    user_id: number
    email: string
    name: string
    membership_label: string
    phone: string
  }
}

type AuthSessionResponse = {
  version: string
  trace_id: string
  request_id: string
  status: string
  session: AuthSessionPayload
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

function mapUser(payload: AuthSessionPayload['user']): MySessionUser {
  return {
    userId: payload.user_id,
    email: payload.email,
    name: payload.name,
    membershipLabel: payload.membership_label,
    phone: payload.phone,
  }
}

export async function loginWithPassword(email: string, password: string) {
  const requestContext = createRequestContext()
  const response = await fetchJson<AuthSessionResponse>(joinUrl(resolveBffBaseUrl(), '/auth/login'), {
    method: 'POST',
    headers: requestContext.headers,
    body: {
      version: 'v1',
      email,
      password,
    },
  })
  return {
    sessionId: response.session.session_id,
    expiresAt: response.session.expires_at,
    user: mapUser(response.session.user),
  }
}

export async function fetchCurrentSession() {
  const requestContext = createRequestContext()
  const response = await fetchJson<AuthSessionResponse>(joinUrl(resolveBffBaseUrl(), '/auth/session'), {
    method: 'GET',
    headers: requestContext.headers,
  })
  return {
    sessionId: response.session.session_id,
    expiresAt: response.session.expires_at,
    user: mapUser(response.session.user),
  }
}

export async function logoutSession() {
  const requestContext = createRequestContext()
  await fetchJson(joinUrl(resolveBffBaseUrl(), '/auth/logout'), {
    method: 'POST',
    headers: requestContext.headers,
    body: {},
  })
}

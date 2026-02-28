import type { MySessionUser } from '../types/my'

const SESSION_USER_KEY = 'bsl.session.user'
const SESSION_ID_KEY = 'bsl.session.id'

function parseStoredUser(raw: string | null): MySessionUser | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<MySessionUser>
    if (typeof parsed.userId !== 'number' || typeof parsed.name !== 'string' || typeof parsed.email !== 'string') {
      return null
    }
    return {
      userId: parsed.userId,
      name: parsed.name,
      email: parsed.email,
      membershipLabel: typeof parsed.membershipLabel === 'string' ? parsed.membershipLabel : 'WELCOME',
      phone: typeof parsed.phone === 'string' ? parsed.phone : '010-0000-0000',
    }
  } catch {
    return null
  }
}

export function getSessionUser() {
  return parseStoredUser(localStorage.getItem(SESSION_USER_KEY))
}

export function getSessionId() {
  const raw = localStorage.getItem(SESSION_ID_KEY)
  if (!raw) return null
  const trimmed = raw.trim()
  return trimmed.length > 0 ? trimmed : null
}

export function setSession(sessionId: string, user: MySessionUser) {
  localStorage.setItem(SESSION_ID_KEY, sessionId)
  localStorage.setItem(SESSION_USER_KEY, JSON.stringify(user))
}

export function updateSessionUser(next: MySessionUser) {
  localStorage.setItem(SESSION_USER_KEY, JSON.stringify(next))
  return next
}

export function clearSession() {
  localStorage.removeItem(SESSION_ID_KEY)
  localStorage.removeItem(SESSION_USER_KEY)
}

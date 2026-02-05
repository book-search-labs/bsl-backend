export type AdminSettings = {
  defaultSize: number
  timeoutMs: number
  defaultVector: boolean
  defaultDebug: boolean
}

const STORAGE_KEY = 'bsl.admin.settings'

export const DEFAULT_SETTINGS: AdminSettings = {
  defaultSize: 10,
  timeoutMs: 1200,
  defaultVector: true,
  defaultDebug: false,
}

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min
  return Math.min(Math.max(value, min), max)
}

export function loadAdminSettings(): AdminSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<AdminSettings>
    return {
      defaultSize: clampNumber(Number(parsed.defaultSize ?? DEFAULT_SETTINGS.defaultSize), 1, 100),
      timeoutMs: clampNumber(Number(parsed.timeoutMs ?? DEFAULT_SETTINGS.timeoutMs), 100, 60000),
      defaultVector: Boolean(parsed.defaultVector ?? DEFAULT_SETTINGS.defaultVector),
      defaultDebug: Boolean(parsed.defaultDebug ?? DEFAULT_SETTINGS.defaultDebug),
    }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveAdminSettings(next: AdminSettings) {
  const payload: AdminSettings = {
    defaultSize: clampNumber(Number(next.defaultSize), 1, 100),
    timeoutMs: clampNumber(Number(next.timeoutMs), 100, 60000),
    defaultVector: Boolean(next.defaultVector),
    defaultDebug: Boolean(next.defaultDebug),
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  return payload
}

export function resetAdminSettings() {
  localStorage.removeItem(STORAGE_KEY)
  return { ...DEFAULT_SETTINGS }
}

const STORAGE_KEY = 'bsl.recentViews'
const MAX_RECENTS = 10

export type RecentView = {
  docId: string
  titleKo: string | null
  authors: string[]
  viewedAt: number
}

function readStorage(): RecentView[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed.filter((item) => typeof item?.docId === 'string') as RecentView[]
  } catch {
    return []
  }
}

function writeStorage(items: RecentView[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // Ignore storage failures
  }
}

export function getRecentViews(): RecentView[] {
  return readStorage()
}

export function addRecentView(view: RecentView) {
  const items = readStorage().filter((item) => item.docId !== view.docId)
  items.unshift(view)
  writeStorage(items.slice(0, MAX_RECENTS))
}

export function clearRecentViews() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Ignore storage failures
  }
}

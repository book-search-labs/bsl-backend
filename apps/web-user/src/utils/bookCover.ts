export type BookCoverSize = 'S' | 'M' | 'L'

function normalizeIsbn13(value?: string | null) {
  if (!value) return null
  const digits = value.replace(/[^0-9Xx]/g, '').toUpperCase()
  if (digits.length !== 13) return null
  return digits
}

function isValidRemoteUrl(value?: string | null) {
  if (!value) return false
  const trimmed = value.trim()
  if (!trimmed) return false
  return /^(https?:\/\/|data:image\/|blob:|\/)/i.test(trimmed)
}

function escapeSvgText(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

function truncateTitle(value: string) {
  const compact = value.replace(/\s+/g, ' ').trim()
  if (!compact) return '제목 없음'
  return compact.length > 36 ? `${compact.slice(0, 36)}…` : compact
}

function pickPalette(seed: string) {
  const tones = [
    ['#2f3d66', '#5a7bb8'],
    ['#3f4f4a', '#6d8f7e'],
    ['#5a3f2f', '#a47f62'],
    ['#2f4f5a', '#5f96ad'],
    ['#4c3d62', '#7f6ab8'],
    ['#2f4b5f', '#5f7fa6'],
  ]
  const hash = Array.from(seed).reduce((acc, ch) => ((acc << 5) - acc + ch.charCodeAt(0)) | 0, 0)
  return tones[Math.abs(hash) % tones.length]
}

function buildGeneratedCoverDataUrl(title: string, docId?: string | null) {
  const safeTitle = truncateTitle(title)
  const seed = `${docId ?? ''}:${safeTitle}`
  const [start, end] = pickPalette(seed)
  const first = escapeSvgText(safeTitle.slice(0, 12))
  const second = escapeSvgText(safeTitle.slice(12, 24))
  const third = escapeSvgText(safeTitle.slice(24, 36))
  const label = escapeSvgText((docId ?? 'BSL').slice(0, 14))
  const svg = `
<svg xmlns='http://www.w3.org/2000/svg' width='360' height='520' viewBox='0 0 360 520'>
  <defs>
    <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='${start}'/>
      <stop offset='100%' stop-color='${end}'/>
    </linearGradient>
  </defs>
  <rect width='360' height='520' fill='url(#g)'/>
  <rect x='26' y='26' width='308' height='468' rx='22' fill='rgba(255,255,255,0.08)'/>
  <text x='38' y='82' fill='rgba(255,255,255,0.9)' font-size='20' font-weight='700'>BSL BOOKS</text>
  <text x='38' y='206' fill='#ffffff' font-size='40' font-weight='700'>${first}</text>
  <text x='38' y='256' fill='#ffffff' font-size='40' font-weight='700'>${second}</text>
  <text x='38' y='306' fill='#ffffff' font-size='40' font-weight='700'>${third}</text>
  <text x='38' y='472' fill='rgba(255,255,255,0.86)' font-size='18' font-weight='600'>${label}</text>
</svg>
  `.trim()
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

export function buildBookCoverUrl(
  coverUrl?: string | null,
  isbn13?: string | null,
  title?: string | null,
  docId?: string | null,
  size: BookCoverSize = 'L',
) {
  if (isValidRemoteUrl(coverUrl)) {
    return coverUrl!.trim()
  }

  const sourceMode = String(import.meta.env.VITE_BOOK_COVER_SOURCE ?? 'generated').toLowerCase()
  const normalized = normalizeIsbn13(isbn13)
  if (normalized && sourceMode === 'openlibrary') {
    return `https://covers.openlibrary.org/b/isbn/${normalized}-${size}.jpg?default=false`
  }

  const fallbackTitle = (title ?? '').trim() || '도서 표지'
  return buildGeneratedCoverDataUrl(fallbackTitle, docId)
}

export function buildBookCoverFallbackText(title?: string | null) {
  const trimmed = (title ?? '').trim()
  if (!trimmed) return 'BOOK'
  return trimmed.slice(0, 1).toUpperCase()
}

import type { HomePanelItem } from '../api/homePanels'

const EVENT_FALLBACK_BANNER = '/event-banners/event-feature-01.svg'
const NOTICE_FALLBACK_BANNER = '/event-banners/notice-feature-01.svg'

function toText(value?: string | null) {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

export function resolvePanelBannerUrl(item: HomePanelItem) {
  const imageUrl = toText(item.banner_image_url)
  if (imageUrl) {
    return imageUrl
  }
  return item.type === 'NOTICE' ? NOTICE_FALLBACK_BANNER : EVENT_FALLBACK_BANNER
}

export function formatPanelPeriod(item: HomePanelItem) {
  const startsAt = toText(item.starts_at)
  const endsAt = toText(item.ends_at)
  if (!startsAt && !endsAt) {
    return null
  }

  const formatDate = (raw: string) => {
    const date = new Date(raw)
    if (Number.isNaN(date.getTime())) {
      return raw
    }
    return date.toLocaleDateString('ko-KR')
  }

  if (startsAt && endsAt) {
    return `${formatDate(startsAt)} ~ ${formatDate(endsAt)}`
  }
  if (startsAt) {
    return `${formatDate(startsAt)}부터 진행`
  }
  return `${formatDate(endsAt!)}까지`
}

export function splitPanelDetailBody(body?: string | null) {
  const normalized = toText(body)
  if (!normalized) {
    return []
  }
  return normalized
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

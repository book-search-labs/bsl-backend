export const OPEN_FLOATING_CHAT_EVENT = 'bsl:open-floating-chat'

export type OpenFloatingChatDetail = {
  prompt?: string
}

export function openFloatingChatWidget(detail: OpenFloatingChatDetail = {}) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent<OpenFloatingChatDetail>(OPEN_FLOATING_CHAT_EVENT, { detail }))
}

export const SEARCH_RESUBMIT_EVENT = 'bsl:search:resubmit'

export type SearchResubmitDetail = {
  query: string
}

export function dispatchSearchResubmit(query: string) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<SearchResubmitDetail>(SEARCH_RESUBMIT_EVENT, {
      detail: { query },
    }),
  )
}

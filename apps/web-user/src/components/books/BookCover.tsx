import { useEffect, useMemo, useState } from 'react'
import type { BookCoverSize } from '../../utils/bookCover'
import { buildBookCoverFallbackText, buildBookCoverUrl } from '../../utils/bookCover'

type BookCoverProps = {
  title?: string | null
  coverUrl?: string | null
  isbn13?: string | null
  docId?: string | null
  size?: BookCoverSize
  className?: string
  loading?: 'lazy' | 'eager'
}

function joinClassName(...values: Array<string | undefined>) {
  return values.filter(Boolean).join(' ')
}

export default function BookCover({
  title,
  coverUrl,
  isbn13,
  docId,
  size = 'L',
  className,
  loading = 'lazy',
}: BookCoverProps) {
  const [hasError, setHasError] = useState(false)
  const resolvedCoverUrl = useMemo(
    () => buildBookCoverUrl(coverUrl, isbn13, title, docId, size),
    [coverUrl, isbn13, title, docId, size],
  )
  const fallbackText = useMemo(() => buildBookCoverFallbackText(title), [title])
  const alt = title?.trim() ? `${title} 표지` : '도서 표지'

  useEffect(() => {
    setHasError(false)
  }, [resolvedCoverUrl])

  if (!resolvedCoverUrl || hasError) {
    return (
      <div className={joinClassName('book-cover-fallback', className)} aria-label={alt}>
        <span>{fallbackText}</span>
      </div>
    )
  }

  return (
    <img
      className={joinClassName('book-cover-image', className)}
      src={resolvedCoverUrl}
      alt={alt}
      loading={loading}
      onError={() => setHasError(true)}
    />
  )
}

export type ChatBookCandidate = {
  rank: number | null
  title: string
  author: string | null
  docId: string
  similarity: number | null
  raw: string
}

const DOC_ID_REGEX = /\b(?:nlk:[A-Za-z0-9._-]+|[A-Za-z]+:[A-Za-z0-9._-]{4,})\b/g

function parseSimilarity(line: string) {
  const match = line.match(/유사도\s*([0-9]+(?:\.[0-9]+)?)/i)
  if (!match) return null
  const value = Number(match[1])
  return Number.isFinite(value) ? value : null
}

function cleanTitle(value: string) {
  return value
    .replace(/^['"“”‘’]+|['"“”‘’]+$/g, '')
    .replace(/\s*[·•]\s*$/, '')
    .trim()
}

function parseCandidate(line: string): ChatBookCandidate | null {
  const raw = line.trim()
  if (!raw) return null

  const rankMatch = raw.match(/^(\d+)\s*[).]/)
  const rank = rankMatch ? Number.parseInt(rankMatch[1], 10) : null
  const body = raw.replace(/^\d+\s*[).]\s*/, '').trim()
  if (!body) return null

  const docMatches = Array.from(body.matchAll(DOC_ID_REGEX))
  if (docMatches.length === 0) return null
  const docId = docMatches[docMatches.length - 1]?.[0]?.trim()
  if (!docId) return null

  const similarity = parseSimilarity(body)
  const docIndex = body.indexOf(docId)
  let title = body
  let author: string | null = null

  if (docIndex >= 0) {
    const beforeDocId = body.slice(0, docIndex).trim()
    const openParenIndex = beforeDocId.lastIndexOf('(')
    if (openParenIndex > 0) {
      title = beforeDocId.slice(0, openParenIndex).trim()
      const insideParen = beforeDocId.slice(openParenIndex + 1).trim()
      const slashIndex = insideParen.lastIndexOf('/')
      if (slashIndex >= 0) {
        author = insideParen.slice(0, slashIndex).trim() || null
      } else if (insideParen) {
        author = insideParen
      }
    } else {
      const slashIndex = beforeDocId.lastIndexOf('/')
      if (slashIndex > 0) {
        title = beforeDocId.slice(0, slashIndex).trim()
        const maybeAuthor = beforeDocId.slice(slashIndex + 1).trim()
        author = maybeAuthor && maybeAuthor !== docId ? maybeAuthor : null
      } else {
        title = beforeDocId
      }
    }
  }

  title = cleanTitle(title)
  if (!title) {
    title = docId
  }

  return {
    rank,
    title,
    author,
    docId,
    similarity,
    raw,
  }
}

export function parseChatBookCandidates(content: string) {
  if (!content) return []
  const lines = content.split('\n')
  const parsed: ChatBookCandidate[] = []
  const seenDocIds = new Set<string>()

  for (const line of lines) {
    const candidate = parseCandidate(line)
    if (!candidate) continue
    if (seenDocIds.has(candidate.docId)) continue
    seenDocIds.add(candidate.docId)
    parsed.push(candidate)
  }

  return parsed
}

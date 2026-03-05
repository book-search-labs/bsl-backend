export type ChatOrderCandidate = {
  rank: number | null
  orderId: number
  orderNo: string | null
  status: string | null
  amount: string | null
  title: string | null
  raw: string
}

function parseOrderCandidate(line: string): ChatOrderCandidate | null {
  const raw = line.trim()
  if (!raw) return null
  if (!/^\d+\)\s*/.test(raw)) return null
  if (!raw.includes("주문ID")) return null

  const orderIdMatch = raw.match(/주문ID\s*(\d+)/)
  if (!orderIdMatch) return null
  const orderId = Number.parseInt(orderIdMatch[1], 10)
  if (!Number.isFinite(orderId) || orderId <= 0) return null

  const rankMatch = raw.match(/^(\d+)\)/)
  const rank = rankMatch ? Number.parseInt(rankMatch[1], 10) : null
  const body = raw.replace(/^\d+\)\s*/, "").trim()
  const segments = body.split("·").map((segment) => segment.trim()).filter(Boolean)

  const orderNo = segments[0] ?? null
  const status = segments[1] ?? null
  const amount = segments.find((segment) => /원$/.test(segment)) ?? null
  const titleMatch = raw.match(/대표도서\s*(.+?)\s*·\s*주문ID\s*\d+/)
  const title = titleMatch?.[1]?.trim() || null

  return {
    rank,
    orderId,
    orderNo,
    status,
    amount,
    title,
    raw,
  }
}

export function parseChatOrderCandidates(content: string) {
  if (!content) return []
  const lines = content.split("\n")
  const parsed: ChatOrderCandidate[] = []
  const seen = new Set<number>()
  for (const line of lines) {
    const candidate = parseOrderCandidate(line)
    if (!candidate) continue
    if (seen.has(candidate.orderId)) continue
    seen.add(candidate.orderId)
    parsed.push(candidate)
  }
  return parsed
}


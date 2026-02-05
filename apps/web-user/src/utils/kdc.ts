import type { KdcCategoryNode } from '../api/categories'

export function flattenKdcCategories(nodes: KdcCategoryNode[]): Map<string, KdcCategoryNode> {
  const map = new Map<string, KdcCategoryNode>()
  const visit = (node: KdcCategoryNode) => {
    if (!node) return
    if (typeof node.code === 'string') {
      map.set(node.code, node)
    }
    if (Array.isArray(node.children)) {
      node.children.forEach(visit)
    }
  }
  nodes.forEach(visit)
  return map
}

export function collectKdcDescendantIds(node: KdcCategoryNode | null | undefined): number[] {
  const ids: number[] = []
  const visit = (item: KdcCategoryNode) => {
    if (!item) return
    if (typeof item.id === 'number') {
      ids.push(item.id)
    }
    if (Array.isArray(item.children)) {
      item.children.forEach(visit)
    }
  }
  if (node) {
    visit(node)
  }
  return ids
}

export function getTopLevelKdc(nodes: KdcCategoryNode[]): KdcCategoryNode[] {
  if (!Array.isArray(nodes)) return []
  return nodes.filter((node) => node && node.depth === 0)
}

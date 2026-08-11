type IdNode = { id: string }
type IdLink = { source: string; target: string }

function buildAdjacency(nodes: IdNode[], links: IdLink[]) {
  const adj = new Map<string, string[]>()
  for (const n of nodes) adj.set(n.id, [])
  for (const l of links) {
    adj.get(l.source)?.push(l.target)
    adj.get(l.target)?.push(l.source)
  }
  return adj
}

export function freeLayout(nodes: IdNode[], links: IdLink[]) {
  const adjacency = buildAdjacency(nodes, links)
  const positions = new Map<string, { x: number; y: number }>()
  const visited = new Set<string>()
  const SX = 260
  const SY = 220
  let col = 0

  function dfs(id: string, row: number) {
    if (visited.has(id)) return
    visited.add(id)
    positions.set(id, { x: col * SX, y: row * SY })
    col++
    for (const neighbor of adjacency.get(id) || []) {
      if (!visited.has(neighbor)) dfs(neighbor, row + 1)
    }
  }

  for (const n of nodes) {
    if (!visited.has(n.id)) dfs(n.id, 0)
  }
  return positions
}

export function treeLayout(nodes: IdNode[], links: IdLink[]) {
  const adjacency = buildAdjacency(nodes, links)
  const SX = 260
  const SY = 200

  let root = nodes[0]?.id || ''
  let maxDeg = 0
  for (const [id, neighbors] of adjacency) {
    if (neighbors.length > maxDeg) { maxDeg = neighbors.length; root = id }
  }

  const positions = new Map<string, { x: number; y: number }>()
  const visited = new Set<string>()
  const levelNodes = new Map<number, string[]>()
  const queue: { id: string; level: number }[] = [{ id: root, level: 0 }]
  visited.add(root)

  while (queue.length > 0) {
    const { id, level } = queue.shift()!
    const children = levelNodes.get(level) || []
    children.push(id)
    levelNodes.set(level, children)
    for (const neighbor of adjacency.get(id) || []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor)
        queue.push({ id: neighbor, level: level + 1 })
      }
    }
  }

  for (const [level, ids] of levelNodes) {
    const totalWidth = (ids.length - 1) * SX
    const startX = -totalWidth / 2
    ids.forEach((id, i) => positions.set(id, { x: startX + i * SX, y: level * SY }))
  }

  let row = levelNodes.size
  let col = -(nodes.length * SX) / 4
  for (const n of nodes) {
    if (!positions.has(n.id)) {
      positions.set(n.id, { x: col, y: row * SY })
      col += SX
      if (col > (nodes.length * SX) / 4) { col = -(nodes.length * SX) / 4; row++ }
    }
  }

  return positions
}

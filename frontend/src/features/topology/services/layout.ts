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

/** Pick the node with the most connections, or the first node. */
function pickRoot(nodes: IdNode[], adj: Map<string, string[]>): string {
  let root = nodes[0]?.id || ''
  let maxDeg = 0
  for (const [id, neighbors] of adj) {
    if (neighbors.length > maxDeg) { maxDeg = neighbors.length; root = id }
  }
  return root
}

/** BFS level assignment starting from root. */
function bfsLevels(root: string, adj: Map<string, string[]>): Map<string, number> {
  const levels = new Map<string, number>()
  const queue: string[] = [root]
  levels.set(root, 0)
  while (queue.length > 0) {
    const id = queue.shift()!
    const level = levels.get(id)!
    for (const neighbor of adj.get(id) || []) {
      if (!levels.has(neighbor)) {
        levels.set(neighbor, level + 1)
        queue.push(neighbor)
      }
    }
  }
  return levels
}

export function freeLayout(nodes: IdNode[], links: IdLink[]) {
  const adjacency = buildAdjacency(nodes, links)
  const positions = new Map<string, { x: number; y: number }>()
  const visited = new Set<string>()
  const SX = 360
  const SY = 280
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
  const SX = 360
  const SY = 260

  const root = pickRoot(nodes, adjacency)

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

/**
 * Circle layout: arrange all nodes in a single ring.
 * Connected nodes are placed near each other via BFS ordering.
 */
export function circleLayout(nodes: IdNode[], links: IdLink[]) {
  const adjacency = buildAdjacency(nodes, links)
  const positions = new Map<string, { x: number; y: number }>()
  const count = nodes.length
  if (count === 0) return positions

  const radius = Math.max(220, count * 30)
  const root = pickRoot(nodes, adjacency)
  const levels = bfsLevels(root, adjacency)

  // Order nodes by BFS level, then by degree (most connected first within level)
  const ordered = [...nodes].sort((a, b) => {
    const la = levels.get(a.id) ?? 9999
    const lb = levels.get(b.id) ?? 9999
    if (la !== lb) return la - lb
    return (adjacency.get(b.id)?.length ?? 0) - (adjacency.get(a.id)?.length ?? 0)
  })

  ordered.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2
    positions.set(node.id, {
      x: Math.round(radius * Math.cos(angle)),
      y: Math.round(radius * Math.sin(angle)),
    })
  })

  return positions
}

/**
 * Radial layout: root at center, children arranged in concentric rings
 * by BFS level. Best for hierarchical network topologies.
 */
export function radialLayout(nodes: IdNode[], links: IdLink[]) {
  const adjacency = buildAdjacency(nodes, links)
  const positions = new Map<string, { x: number; y: number }>()
  if (nodes.length === 0) return positions

  const root = pickRoot(nodes, adjacency)
  const levels = bfsLevels(root, adjacency)

  // Group nodes by level
  const byLevel = new Map<number, string[]>()
  const unvisited: string[] = []
  for (const n of nodes) {
    const level = levels.get(n.id)
    if (level === undefined) {
      unvisited.push(n.id)
    } else {
      const arr = byLevel.get(level) || []
      arr.push(n.id)
      byLevel.set(level, arr)
    }
  }

  // Place root at center
  positions.set(root, { x: 0, y: 0 })

  // Place each level in a concentric ring
  const baseRadius = 220
  const ringSpacing = 260
  for (const [level, ids] of byLevel) {
    if (level === 0) continue
    const radius = baseRadius + (level - 1) * ringSpacing
    // Sort within ring by degree (most connected first)
    ids.sort((a, b) => (adjacency.get(b)?.length ?? 0) - (adjacency.get(a)?.length ?? 0))
    ids.forEach((id, i) => {
      const angle = (2 * Math.PI * i) / ids.length - Math.PI / 2
      positions.set(id, {
        x: Math.round(radius * Math.cos(angle)),
        y: Math.round(radius * Math.sin(angle)),
      })
    })
  }

  // Place unvisited nodes (disconnected components) in a grid below
  let col = 0
  let row = 0
  const gridX = 200
  const gridY = 180
  const maxY = Math.max(...[...byLevel.keys()].map(l => baseRadius + l * ringSpacing), 0) + 300
  for (const id of unvisited) {
    positions.set(id, { x: col * gridX, y: maxY + row * gridY })
    col++
    if (col > 5) { col = 0; row++ }
  }

  return positions
}

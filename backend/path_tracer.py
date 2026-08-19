"""Layer-3 path analysis via graph shortest-path (Sprint 10).

Builds an undirected graph from stored topology links and runs BFS to
find the shortest path between any two device IPs.
"""

from __future__ import annotations

from collections import deque


def build_path(
    links: list[dict],
    source: str,
    target: str,
) -> dict:
    """Return the shortest path between *source* and *target*.

    *links* is a list of dicts with keys ``source``, ``target``,
    ``source_interface``, ``target_interface``, ``protocol``,
    ``source_hostname``, ``target_hostname``.

    Returns ``{path: [...], hops: N}`` or ``{path: [], hops: 0, error: str}``
    when no path exists.
    """
    if source == target:
        return {"path": [], "hops": 0, "error": "source and target are the same"}

    # Build adjacency list
    adj: dict[str, list[tuple[str, dict]]] = {}
    for l in links:
        s = l["source"]
        t = l["target"]
        if not s or not t:
            continue
        adj.setdefault(s, []).append((t, l))
        adj.setdefault(t, []).append((s, l))

    if source not in adj or target not in adj:
        return {"path": [], "hops": 0,
                "error": f"{'source' if source not in adj else 'target'} not found in topology"}

    # BFS — find the shortest path
    parent: dict[str, tuple[str, dict] | None] = {source: None}
    queue = deque([source])
    found = False

    while queue and not found:
        node = queue.popleft()
        for neighbor, edge in adj.get(node, []):
            if neighbor not in parent:
                parent[neighbor] = (node, edge)
                if neighbor == target:
                    found = True
                    break
                queue.append(neighbor)

    if not found:
        return {"path": [], "hops": 0,
                "error": f"no route from {source} to {target}"}

    # Reconstruct path
    path: list[dict] = []
    cur = target
    while parent[cur] is not None:
        prev, edge = parent[cur]  # type: ignore[index]
        path.append({
            "source": edge["source"],
            "target": edge["target"],
            "source_hostname": edge.get("source_hostname", ""),
            "target_hostname": edge.get("target_hostname", ""),
            "source_interface": edge.get("source_interface", ""),
            "target_interface": edge.get("target_interface", ""),
            "protocol": edge.get("protocol", ""),
        })
        cur = prev
    path.reverse()
    return {"path": path, "hops": len(path)}


def articulation_points(nodes: list[str], links: list[dict]) -> set[str]:
    """Return the set of articulation points (single points of failure).

    A vertex is an articulation point if removing it splits the graph into
    more connected components — i.e. that device's failure partitions the
    network. Uses Tarjan's O(V + E) DFS.

    *nodes* is a list of device IPs; *links* is a list of dicts with
    ``source``/``target`` keys.
    """
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for l in links:
        s, t = l.get("source"), l.get("target")
        if s in adj and t in adj and s != t:
            adj[s].append(t)
            adj[t].append(s)

    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str] = {}
    aps: set[str] = set()
    timer = [0]

    def dfs(u: str) -> None:
        children = 0
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in adj[u]:
            if v not in disc:
                parent[v] = u
                children += 1
                dfs(v)
                low[u] = min(low[u], low[v])
                if u not in parent and children > 1:
                    aps.add(u)
                if u in parent and low[v] >= disc[u]:
                    aps.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for n in nodes:
        if n not in disc:
            dfs(n)
    return aps

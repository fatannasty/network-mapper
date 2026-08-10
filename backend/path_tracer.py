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

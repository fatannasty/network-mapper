"""VMware VeloCloud SD-WAN Orchestrator REST API client.

Provides edge inventory import with site/link data for Sprint 13 data quality.
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Optional


class VeloCloudError(Exception):
    pass


def _request(base_url: str, token: str, endpoint: str,
             body: Optional[dict] = None, timeout: float = 30.0) -> dict | list:
    """Call a VeloCloud Orchestrator REST endpoint and return the parsed JSON."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{base_url.rstrip('/')}/portal/rest/{endpoint.lstrip('/')}"
    data = json.dumps(body or {}).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Token {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        raise VeloCloudError(f"Invalid JSON: {e}") from e
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500] if e.fp else str(e)
        raise VeloCloudError(f"HTTP {e.code}: {msg}") from e
    except OSError as e:
        raise VeloCloudError(f"Connection failed: {e}") from e


def get_edges(base_url: str, token: str, timeout: float = 60.0) -> list[dict]:
    """Return all enterprise edges with site info and recent WAN links.

    The ``with`` array requests embedded site objects and per-edge WAN link
    data so a single call returns everything needed for device matching,
    site attribution, and interface extraction.
    """
    body = {"with": ["site", "recentLinks"]}
    result = _request(base_url, token, "enterprise/getEnterpriseEdges",
                      body=body, timeout=timeout)
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "error" in result:
        raise VeloCloudError(f"API error: {result['error']}")
    return []


def get_edge_detail(base_url: str, token: str, edge_id: int,
                    timeout: float = 30.0) -> dict:
    """Return a single edge with full detail including WAN interfaces."""
    return _request(base_url, token, "edge/getEdge",
                    body={"id": edge_id}, timeout=timeout)


def get_edge_config(base_url: str, token: str, edge_id: int,
                    timeout: float = 30.0) -> list[dict]:
    """Return the configuration stack for an edge."""
    return _request(base_url, token, "edge/getEdgeConfigurationStack",
                    body={"edgeId": edge_id}, timeout=timeout)

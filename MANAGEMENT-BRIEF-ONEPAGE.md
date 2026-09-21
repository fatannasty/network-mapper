# Network Mapper — One-Page Brief

**A single platform to see, monitor, and report on the Amtrak network.**

## What it does
- **Imports** devices from Catalyst Center, SNMP (v2c/v3), Meraki, and VeloCloud SD-WAN — per site or the whole network.
- **Topology** — interactive map of 3,900+ devices with health badges, single-point-of-failure markers, and VLAN 90 tags.
- **Monitor** — one live page: every device type (switches, access points, VeloCloud edges, routers) with status, latency, interface health, and per-site rollups.
- **Executive dashboard** — health score, site freshness, risks, busiest links, trend.
- **Config & compliance** — SSH config collection, color-coded diffs, change detection.
- **Utilization & alerts** — interface traffic trends; flapping/down/SPOF alerts (in-app + email).
- **Reporting** — one-click executive reports (PDF/HTML with charts), scheduled & emailed; CSV exports.

## Built with
- **Backend:** Python 3.11 · FastAPI · pure-Python SNMP/SSH · SQLite (PostgreSQL-ready)
- **Frontend:** TypeScript · React 19 · Tailwind · React Flow
- **Quality:** 239 backend tests + 7 e2e browser tests · Docker/nginx · CI

## Security
- Role-based access (admin / operator / viewer) on every API
- Encrypted credential vault (AES) · scrypt password hashing
- Signed bearer tokens + httpOnly cookies · hashed, revocable API tokens
- Login rate limiting · secrets via environment (never committed)

## Active Directory
**Yes — integrable.** Recommended: **LDAPS with AD group → role mapping**
(quickest), then **Entra ID / SAML SSO** for true corporate sign-on + MFA.

## 5-minute demo
Monitor → Executive dashboard → Topology (site view) → Executive report (PDF).

---
*Details: `MANAGEMENT-BRIEF.md` · technical: `PRESENTATION-TECH.md`*
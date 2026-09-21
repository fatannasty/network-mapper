# Network Mapper — Management Briefing Reference

*Reference guide for the demo meeting. High-level, with the technical specifics
your attendees may ask for.*

---

## 1. Application overview

**Network Mapper** is a single platform that sees, monitors, and reports on the
Amtrak network. It imports devices from multiple sources, shows them on an
interactive map, tracks health in real time, and turns it all into
management-ready reports.

**What it does**
- **Import** — brings in devices from Cisco Catalyst Center, SNMP discovery
  (v2c/v3), Meraki, and VeloCloud SD-WAN. Scoped to a site or the whole network.
- **Topology** — an interactive map of 3,900+ devices with health badges
  (up/degraded/down/flapping), single-point-of-failure markers, and VLAN 90 tags.
- **Monitor** — a single live page showing every device type (switches, access
  points, VeloCloud edges, routers) with operational status, latency, interface
  health, and per-site rollups — plus drill-down to the specific down interfaces.
- **Dashboards** — an Executive scorecard (health score, site freshness, risks,
  busiest links, trend) and an Operations view for engineers.
- **Configuration & compliance** — SSH config collection, color-coded config
  diffs, and network-wide change detection.
- **Utilization** — interface traffic trends over time.
- **Alerts & notifications** — flapping/down/SPOF alerts in-app and by email.
- **Reporting** — one-click executive reports (PDF/HTML with charts),
  scheduled and emailed; CSV exports for spreadsheets.
- **Automation** — API tokens and scheduled background jobs keep data fresh.

**Demo flow (5 min):** open **Monitor** → **Executive dashboard** → **Topology**
(site view) → **Executive reports** (PDF).

---

## 2. Technology stack

| Layer | Technology |
|-------|-----------|
| Backend | **Python 3.11**, FastAPI, SQLAlchemy 2, uvicorn |
| Network integration | Pure-**Python SNMP** (v1/v2c/v3 — no external daemon) and SSH |
| Frontend | **TypeScript**, React 19, Vite, Tailwind CSS, React Flow |
| Database | SQLite (default) — **PostgreSQL-ready** (no code changes) |
| Reporting | PDF via reportlab (Python); HTML; CSV/Excel-compatible |
| Deployment | **Docker Compose**, nginx reverse proxy, GitHub Actions CI |
| Testing | 239 backend tests + 7 end-to-end browser tests |

**Short answer to "what language is it built with?":** Python (backend/network
automation) and TypeScript (web frontend).

---

## 3. Security features implemented

- **Role-based access control (RBAC)** — three roles (admin / operator / viewer)
  enforced on every API endpoint.
- **Authentication** — signed bearer tokens (HMAC-SHA256, 12-hour expiry) with an
  **httpOnly session cookie** (not exposed to browser scripts).
- **Passwords** — hashed with **scrypt** (strong, memory-hard).
- **Credential vault** — SNMP/SSH credentials stored encrypted at rest
  (**Fernet** = AES-128-CBC + HMAC-SHA256).
- **API tokens** — for automation; stored as SHA-256 hashes (never plaintext),
  revocable, role-scoped.
- **Login rate limiting** — throttles brute-force attempts.
- **Secrets management** — signing/encryption keys come from environment
  variables (`SECRET_KEY`, `ENCRYPTION_KEY`); secrets and DB files are gitignored.
- **Transport** — designed to run behind HTTPS in production (see below).

---

## 4. Future security enhancements to consider

- **Active Directory / SSO** — the top item; see section 5.
- **HTTPS everywhere** — terminate TLS at the reverse proxy (currently plain HTTP
  in the dev/Docker reference; add TLS/certificates for production).
- **MFA** for admin/operator accounts.
- **Session timeout / idle logout**.
- **Audit log expansion** — record who did what (config changes, exports, user
  actions) for compliance.
- **Secrets management upgrade** — external vault (HashiCorp Vault / cloud secret
  manager) instead of environment variables.
- **API token lifecycle** — expiry/rotation policy.
- **Per-site credential scoping** — limit which credentials a role can use.
- **Dependency & vulnerability scanning** in CI.

---

## 5. Active Directory (AD) integration

**Yes — this app can integrate with Active Directory.** Authentication today is
username/password against an app-managed user table with role mapping
(admin/operator/viewer), so AD is a natural fit. Three options:

1. **LDAP/LDAPS against AD (recommended, quickest)**
   - Users authenticate with their corporate credentials.
   - **AD security groups map to app roles** (e.g., "Network Ops" → operator).
   - Straightforward to add; keeps local accounts for service/break-glass use.

2. **SAML 2.0 / OpenID Connect SSO (e.g., Microsoft Entra ID / Azure AD)**
   - True corporate single sign-on in the browser.
   - Best for "sign in with your corporate identity," central MFA, and policy
     controls. Requires an IdP integration (metadata + app registration).

3. **Hybrid** — keep local accounts for automation/service identities and enable
   AD/SSO for human users.

**Recommendation:** start with **LDAPS + AD group→role mapping** for a fast win,
then layer **Entra ID (SAML/OIDC) SSO** if central sign-on and MFA are required.

---

*For deeper technical detail: `PRESENTATION-TECH.md` · deployment: `UBUNTU-DEPLOY.md`.*
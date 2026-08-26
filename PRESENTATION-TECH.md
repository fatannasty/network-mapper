# Network Mapper — Technical Deep Dive (for reviewers)

Companion to `PRESENTATION.md`. Goes deeper on architecture, data model,
algorithms, security, performance, automation, and deployment so reviewers can
ask-and-answer specifics. Everything below is implemented, tested, and running.

---

## 1. Architecture

- **Backend:** FastAPI (Python 3.11) served by uvicorn; SQLAlchemy 2 ORM.
  - SQLite by default (`network_mapper.db`); PostgreSQL-ready via `DATABASE_URL`
    (psycopg). No code changes required to switch engines.
- **Frontend:** React 19 + Vite 8 + Tailwind 4; topology rendered with
  **@xyflow/react (React Flow 12)**. Theme system with Light / Dark / NOC
  palettes driven by CSS custom properties.
- **Deployment:** Docker Compose — `backend` (uvicorn :8000, healthcheck) +
  `frontend` (nginx :8080 proxying `/api` → `backend`). SQLite persists on the
  `app-data` volume. See `UBUNTU-DEPLOY.md`.
- **Background services** (asyncio loops started in FastAPI lifespan; each runs
  DB work in a threadpool so the event loop stays responsive):

  | Loop | Default interval | Env override | Purpose |
  |------|------------------|--------------|---------|
  | Latency poller | 60 s | `LATENCY_POLL_INTERVAL` | up/down + flapping state |
  | Utilization sampler | 300 s | `UTIL_POLL_INTERVAL`, `UTIL_POLL_BATCH` | interface rate trends |
  | Alert check | 300 s | `ALERT_CHECK_INTERVAL`, `ALERT_COOLDOWN_HOURS` | flapping/down/SPOF notifications |
  | Health snapshot | 3600 s | `HEALTH_HISTORY_INTERVAL` | executive score history |
  | Config collection | off | `CONFIG_COLLECT_INTERVAL`, `CONFIG_COLLECT_BATCH` | nightly config backups |
  | Exec report scheduler | off | `EXEC_REPORT_SCHEDULE` (hourly/daily/weekly) | auto report generation |

---

## 2. Data model (core tables)

- `devices` — keyed on `ip` (unique); hostname, vendor, model, `device_type`,
  `site`, `catalyst_id`, `latency_ms`, `vlan_90` (nullable boolean).
- `interfaces` — per-device IF-MIB rows: `ifIndex`, `ifName`, `ifDescr`,
  `ifOperStatus`, `ifAdminStatus`, plus dot1q `vlan_id` / `vlan_name`.
- `links` — `scan_id`, `endpoint_a`, `endpoint_b`, `interface_a/b`, `protocol`
  (lldp | cdp | cdp-lldp | catalyst | poe | velocloud | velocloud-lan), `hostname_a/b`.
- `scan_jobs` — provenance for every import/scans, with `scan_kind`
  (subnet | full_env | site | validation | meraki | velocloud …).
- `device_configs` — SSH-collected running configs with `collected_by` /
  `collected_at` (audit trail).
- `device_status_history` — reachability transitions (feeds flapping detection).
- `site_mappings` — hostname-prefix → site rules for blank-site backfill.
- `credentials` — vaulted SNMP/SSH secrets (Fernet-encrypted at rest).
- `api_tokens` — long-lived bearer tokens (sha256-hashed, never plaintext).
- `notifications` — alert/notification records (flapping | down | spof).
- `interface_utilization` — counter/rate samples for trend charts.
- `health_snapshots` — hourly executive score history.
- `exec_reports` — archived executive reports (HTML + PDF).
- `users` — RBAC accounts (admin / operator / viewer).

---

## 3. Topology engine

- **Layouts:** Tree / Radial / Circle / Free — all O(V+E) BFS/DFS passes in the
  frontend (`services/layout.ts`), no force simulation, so 3,900+ nodes lay out
  in milliseconds.
- **SPOF detection:** articulation points via **Tarjan's algorithm** (O(V+E))
  over the topology link graph (`path_tracer.py`).
- **Operational state:** per-device status derived from interface `ifOperStatus`
  counts (up / degraded / down), with a latency fallback when no interfaces exist.
- **Flapping:** a device is flagged flapping after **≥3 up↔down transitions in a
  10-minute window**, tracked in `device_status_history`.
- **Link filtering:** `NON_TOPOLOGY_PROTOCOLS` excludes VeloCloud **WAN/overlay**
  links (`velocloud`) and self-loops; physical LAN links (`velocloud-lan`) render.
- **Cross-scan expansion:** a site/default view pulls in neighbors via any
  topology link across all scans, so links discovered by different tools coexist.

---

## 4. SNMP (pure-Python, no external daemon)

- **v1/v2c client** (`snmp.py`): GET/GETBULK walks of IF-MIB, ifX-MIB, LLDP/CDP
  tables, dot1q VLAN tables.
- **SNMPv3 USM client** (`snmpv3.py`), implemented from RFC 3412/3414/3826:
  engine discovery, RFC 3414 key localization, HMAC auth (MD5/SHA), privacy
  (DES / AES-128-CBC), GETBULK with `notInTimeWindows` resync.
- **Utilization:** samples `ifHCInOctets` / `ifHCOutOctets`, derives bits/sec
  from consecutive-sample deltas, prunes older than 30 days.
- **VLAN discovery:** dot1q OIDs parsed into `vlan_id` / `vlan_name` per interface
  (v2c + v3 paths).

---

## 5. Config collection, diff & change detection

- **Collection:** SSH via paramiko interactive shell (`terminal length 0` to
  avoid `--More--`), stores running configs per device with collector + timestamp.
- **Diff:** `GET /api/inventory/config-diff` returns a unified diff
  (Python `difflib`) with add/remove/context classifications.
- **Change detection:** `GET /api/inventory/config-changes` compares each
  device's two newest running configs and reports drift network-wide.
- **VLAN 90:** `detect_vlan90()` scans a running config for VLAN-90 references
  (`interface Vlan90`, `switchport access vlan 90`, `vlan 90`, trunk lists).
  After **every Catalyst import** the flags are recomputed from stored configs +
  interface `vlan_id == 90`, so full re-imports never wipe them.

---

## 6. Security

- **RBAC:** FastAPI dependencies (`authenticated` / `operator` / `admin`).
- **Sessions:** HMAC-SHA256 signed bearer token (12 h TTL) delivered as an
  httpOnly cookie; also accepted as `Authorization: Bearer`.
- **API tokens:** `secrets.token_hex(32)` created on demand, stored **hashed**
  (sha256), revocable, role-scoped, with `last_used_at` tracking.
- **Secrets at rest:** Fernet (AES-128-CBC + HMAC-SHA256) for the credential vault;
  scrypt for password hashing; `SECRET_KEY` / `ENCRYPTION_KEY` from env in prod.
- **Rate limiting:** login throttled at 10 attempts/min (`LOGIN_RATE_LIMIT`).

---

## 7. Performance at scale (measured on live data)

- 3,933 devices · 20,109 interfaces · 42,807 links · 350+ sites.
- **Frontend:** React Flow `onlyRenderVisibleElements`; edge animations only
  ≤500 links; edge labels dropped >1200 links; MiniMap capped at 1500 nodes.
- **Backend:** `/api/topology` TTL cache (60 s, LRU-capped at 32) cut repeat
  loads from ~0.96 s → ~0.17 s; diagram rendering runs in a threadpool.
- **Schedulers** rotate work (utilization batch of 100 devices per pass,
  config collection batch of 50) so nothing blocks the request path.

---

## 8. Reports & automation

- **Executive report:** `GET /api/health/exec` → self-contained HTML + a
  **reportlab PDF** with charts — status donut, coverage-vs-target grouped bars,
  health-trend line, busiest-links horizontal bars — plus site/risk/SPOF tables.
  Each chart is isolated in try/except so a chart failure never breaks the PDF.
- **Scheduling:** `EXEC_REPORT_SCHEDULE=hourly|daily|weekly` auto-generates;
  `SMTP_*` + `REPORT_TO` enable emailing the PDF.
- **Alerts:** flapping/down notifications per device (cooldown-gated) and SPOF as
  a single aggregate advisory gated on count change; in-app bell + optional email.
- **API surface:** `/api/auth/*`, `/api/inventory/*`, `/api/topology/*`,
  `/api/backfill/*`, `/api/catalyst/*`, `/api/meraki/*`, `/api/velocloud/*`,
  `/api/health/*`, `/api/report/executive/*`, `/api/notifications/*`,
  `/api/utilization/*`, `/api/search`, `/api/configs/download`.

---

## 9. Testing & CI

- **Backend:** 236 pytest tests (auth/RBAC, SNMP v2c/v3, scanner, topology, SPOF,
  flapping, reports, config diff, alerts, bulk ops, search, health history).
- **End-to-end:** 7 Playwright tests with mocked APIs (auth flicker regression,
  VLAN 90 flow, bulk ops, executive dashboard, notifications, onboarding tour).
- **CI (GitHub Actions):** backend pytest + frontend build/lint + Playwright e2e
  on every push/PR; fonts installed for diagram rendering.
- Local: `pytest tests/` (236), `npm run build && npm run lint`,
  `npx playwright test` (7).

---

## 10. Deployment notes

- `docker compose up -d --build` → web :8080, api :8000, healthcheck green.
- Critical env: `SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`; operational:
  `UTIL_POLL_INTERVAL`, `ALERT_CHECK_INTERVAL`, `CONFIG_COLLECT_INTERVAL`,
  `EXEC_REPORT_SCHEDULE`, `SMTP_HOST/PORT/USER/PASSWORD/FROM`, `REPORT_TO`.
- Data survives rebuilds on the `app-data` volume; upgrade = `git pull && docker
  compose up -d --build`. Full checklist in `VALIDATION.md`.
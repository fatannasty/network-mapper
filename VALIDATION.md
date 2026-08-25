# Launch Validation Checklist

End-to-end validation of the network-mapper platform before go-live. Each
section lists what to verify and how to initiate it. Run section **7**
(automated) first — it's the cheapest signal.

## 0. Bring up the stack

**Dev:**
```bash
cd /Users/fatannasty/Documents/Daily/network-mapper
npm run start            # backend (uvicorn, port 8000, no reload)
npm run frontend:dev     # frontend (vite, port 5173)
```

**Docker (production-like):**
```bash
SECRET_KEY="$(openssl rand -base64 32)" docker compose up -d --build
# web http://localhost:8080 · api http://localhost:8000
```

**First admin user (if the DB has none):**
```bash
cd backend && .venv/bin/python -c "from database import SessionLocal; import repositories; db=SessionLocal(); repositories.create_user(db,'admin','change-me','admin'); db.close()"
```

**Expect:** `curl -s localhost:8000/health` -> `{"status":"ok",...}`.

---

## 1. Authentication & onboarding

| Check | Initiate | Expect |
|-------|----------|--------|
| Login | Open the app -> sign in | Lands on Topology, no flicker |
| Wrong password | Enter bad creds | "Invalid username or password", **no page reload** |
| Session survives reload | Hard-refresh (Cmd+Shift+R) | Still logged in (cookie) |
| Logout | User menu -> logout | Returns to login; `/api/auth/me` -> 401 |
| Rate limit | 10+ failed logins in a minute | 429 "Too many login attempts" |
| First-run tour | Fresh browser, first login | Help wizard auto-opens (Welcome -> Import -> Topology -> Exports -> Dashboard) |
| Glossary | Sidebar -> Help | Tour + plain-language glossary available anytime |

---

## 2. Discovery & classification

**Initiate:** Ingest -> enter a subnet (e.g. `10.41.36.0/24`) + SNMP community -> run scan.

**Expect:** devices appear with correct vendor/model/device_type; interfaces
populate (`ifOperStatus` up/down).

---

## 3. SNMP Walk (whole network / per site)

**Initiate:** Import -> **SNMP Walk** tab.

**Expect:**
- Scope to a **site** or "Whole network"; toggle **v2c (vault) / v3**; run
  interface+VLAN and/or link walks.
- Summary shows devices OK/failed, interfaces/VLANs walked, LLDP/CDP links found.
- Walked data appears in Topology (interfaces in DeviceDetail, links on the graph)
  and in **Topology -> Export Walk Report** (interfaces+VLAN CSV, links CSV).

---

## 4. Interactive topology — state & SPOF

**Initiate:** Topology page, load a site scan (switch to **Technical** view).

**Expect:**
- Node badges (top-right): `●` up · `◐` degraded · `▼` down · `◍` pulsing = flapping · `○` unknown.
- **SPOF** amber `⚠` (top-left) on single-path devices.
- **VLAN 90** — teal `V90` badge + teal node ring on flagged switches.
- **Simple -> By Subnet** toggle collapses to subnet blocks with counts.
- Down links render red/dashed.

---

## 5. Operational state (latency + flapping)

**Initiate:** Topology -> "Measure Latency" (or wait for the background poller).

**Expect:** devices get `latency_ms`; a device pinged down then up repeatedly
becomes **flapping** after >=3 transitions in 10 min (pulsing badge).

---

## 6. VLAN (needs a real switch)

**Initiate:** run an SNMP walk against a switch with VLANs configured.

**Expect:** DeviceDetail shows teal `VLAN <id> · <name>` chips on interfaces;
switches carrying VLAN 90 are flagged via **Import -> Catalyst -> "Sync VLAN 90
from stored data"** and filtered in Inventory (All / VLAN 90 / No VLAN 90).

---

## 7. Config collection, diff & change detection

**Initiate:** Inventory -> **Collect Configs** on a device/site (SSH, vaulted creds).

**Expect:**
- Config stored with timestamp + collector; DeviceDetail -> **Config history**
  lists collections; pick two to view a color-coded **diff**.
- **Data Quality -> Recent config changes** lists devices whose two newest
  configs differ.

---

## 8. Bulk operations

**Initiate:** Inventory -> select devices (checkbox) -> action bar.

**Expect:** **Collect configs**, **Walk interfaces**, **Walk links**, and
**Assign site** run across the selection with a result message.

---

## 9. Utilization & alerts

**Initiate:** wait for the pollers (default 300s) or restart after configuring.

**Expect:**
- DeviceDetail -> **Link utilization** shows per-interface in/out rate charts
  once the poller has two+ samples.
- **Dashboard -> Executive -> Busiest links** lists top interfaces by traffic.
- **Alerts** — flapping/down/SPOF events appear in the header **bell**; with
  SMTP configured they email. Use the bell's **Run check** to force a check.

---

## 10. Executive dashboard & reports

**Initiate:** Dashboard -> **Executive** toggle.

**Expect:**
- Health banner + score, KPI scorecard (drillable), **Site freshness** table,
  **Risks & issues** and **SPOF** lists, **Busiest links**, **Reports** archive.
- **Generate now** produces an HTML report (and PDF); with `EXEC_REPORT_SCHEDULE`
  set, reports auto-generate (and email when SMTP is configured).

---

## 11. Diagram export (all formats)

**Initiate:** Topology -> "Export Diagram" -> pick a format.

**Expect:**
- **Visio (.vsdx)** — opens in Visio; logo + title block; labels beside icons; editable shapes/connectors.
- **PDF / PNG** — logo, title block, correct fonts, no clipped text.
- **Word (.docx)** — image on a sized page.
- **Large site (Seattle)** — overview + drill-down + AP pages.
- **Preview** thumbnail matches the output.
- **"Executive Package"** — ZIP with PDF + DOCX + CSV.
- **"Export Port Table"** and **"Export Walk Report"** — clean CSVs.

---

## 12. API tokens (automation)

**Initiate:** Admin -> API Tokens -> create a token.

**Expect:** plaintext shown once; `curl -H "Authorization: Bearer <token>" .../api/health/exec`
returns 200; revoking returns 401 for that token.

---

## 13. Automated tests

```bash
cd backend  && .venv/bin/python -m pytest tests/ -q     # expect 231 passed
cd frontend && npm run build && npm run lint            # expect clean
cd frontend && npx playwright test                      # expect 7 passed
```

Also verify the GitHub Actions **CI** run goes green on the latest push.

---

## 14. Deployment / Docker

**Initiate:** `docker compose up -d --build` with a `.env` (secrets, SMTP, report
schedule). See `UBUNTU-DEPLOY.md`.

**Expect:** web on 8080 proxies `/api` to backend; restart the container and
confirm the DB (volume) and login session persist; healthcheck green (`docker ps`).

---

## Suggested order

1. **13** (automated) — cheapest signal.
2. **1 -> 2 -> 4 -> 11** (core app).
3. **3 -> 6 -> 7 -> 8** (SNMP/config features).
4. **5 -> 9 -> 10** (data-dependent: latency, utilization, alerts).
5. **12 -> 14** last (automation + deployment).
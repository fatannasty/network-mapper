# Launch Validation Checklist

End-to-end validation of the network-mapper platform before go-live. Each
section lists what to verify and how to initiate it.

## 0. Bring up the stack

**Dev:**
```bash
cd /Users/fatannasty/Documents/Daily/network-mapper
npm run start            # backend (uvicorn, port 8000, no reload)
npm run frontend:dev     # frontend (vite, port 5173)
```

**Docker:**
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

## 1. Authentication

| Check | Initiate | Expect |
|-------|----------|--------|
| Login | Open the app -> sign in | Lands on Topology, no flicker |
| Wrong password | Enter bad creds | "Invalid username or password", **no page reload** |
| Session survives reload | Hard-refresh (Cmd+Shift+R) | Still logged in (cookie) |
| Logout | User menu -> logout | Returns to login; `/api/auth/me` -> 401 |
| Rate limit | 10+ failed logins in a minute | 429 "Too many login attempts" |

---

## 2. Discovery & classification

**Initiate:** Ingest -> enter a subnet (e.g. `10.41.36.0/24`) + SNMP community -> run scan.

**Expect:** devices appear with correct vendor/model/device_type; interfaces
populate (`ifOperStatus` up/down).

---

## 3. Interactive topology — state & SPOF

**Initiate:** Topology page, load a site scan.

**Expect:**
- Node badges (top-right): `●` up · `◐` degraded · `▼` down · `◍` pulsing = flapping · `○` unknown.
- **SPOF** amber `⚠` (top-left) on single-path devices (e.g. the core).
- **Simple -> By Subnet** toggle collapses to subnet blocks with counts.
- Down links render red/dashed.

---

## 4. Operational state (latency + flapping)

**Initiate:** Topology -> "Measure Latency" (or wait for the background poller).

**Expect:** devices get `latency_ms`; a device pinged down then up repeatedly
becomes **flapping** after >=3 transitions in 10 min (verify via the pulsing badge).

---

## 5. VLAN (needs a real switch)

**Initiate:** run a discovery against a switch with VLANs configured.

**Expect:** DeviceDetail shows teal `VLAN <id> · <name>` chips on interfaces.

**If empty:** the dot1q OIDs in `backend/vlan.py` may need adjustment for your
hardware — capture `snmpwalk -v2c -c <community> <ip> 1.3.6.1.2.1.17.7.1.4.3`
output and share it.

---

## 6. Diagram export (all formats)

**Initiate:** Topology -> "Export Diagram" -> pick a format.

**Expect:**
- **Visio (.vsdx)** — opens in Visio; Amtrak logo top-left + title block; labels beside icons; editable shapes/connectors.
- **PDF / PNG** — logo, title block, correct fonts (Arial), no clipped text.
- **Word (.docx)** — image on a sized page.
- **Large site (Seattle)** — overview page + drill-down pages + AP page.
- **Preview** thumbnail in the dialog matches the output.
- **"Executive Package"** — downloads a ZIP with PDF + DOCX + CSV.
- **"Export Port Table"** — CSV with device -> port -> neighbor.

---

## 7. Automated tests

```bash
cd backend  && .venv/bin/python -m pytest tests/ -q     # expect 218 passed
cd frontend && npm run build && npm run lint            # expect clean
cd frontend && npx playwright test                      # expect 2 passed
```

Also verify the GitHub Actions **CI** run goes green on the latest push.

---

## 8. Deployment / Docker

**Initiate:** `docker compose up -d --build`.

**Expect:** web on 8080 proxies `/api` to backend; restart the container and
confirm the DB (volume) and login session persist; healthcheck green (`docker ps`).

---

## Suggested order

Run **7** (automated) first — the cheapest signal. Then **1 -> 2 -> 3 -> 6**
(core app), then **4 -> 5** (data-dependent), then **8** last.

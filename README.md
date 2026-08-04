# Network Discovery and Topology Mapping Platform

A NetBrain-style discovery and topology application for switches, routers,
SD-WAN, and VMware VeloCloud devices. PCs and printers are excluded from
topology output.

Target stack (from the sprint plan):

| Layer      | Technology                  |
|------------|-----------------------------|
| Frontend   | React / Next.js, React Flow |
| Backend    | FastAPI (Python)            |
| Database   | PostgreSQL                  |
| Graph      | Neo4j (optional)            |
| Discovery  | Nmap, SNMPv2c/v3, SSH, APIs |

## Sprint 1 — Discovery and Classification MVP (current)

Deliverables: `scanner.py`, `snmp.py`, `classifier.py`, `main.py`.
Success criteria: accurately identify Cisco, Aruba, Fortinet, and VeloCloud devices.

```
backend/
  main.py         FastAPI app (GET /health, POST /api/discover)
  scanner.py      CIDR parsing, ping sweep, TCP scan, UDP/161 probe, orchestration
  snmp.py         Pure-Python SNMPv2c client (BER encode/decode, no deps)
  classifier.py   Vendor OID map + sysDescr/hostname rules -> vendor/model/type
  tests/          35 unit + integration tests (mock SNMP agent)
```

### Run it

```bash
npm run setup        # or: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm run api          # uvicorn on http://localhost:8000 (reload enabled)
```

### API

```
GET  /health                      -> service status + local IP
POST /api/discover
     { "subnet": "10.0.0.0/24",
       "communities": ["public"],
       "exclude_pcs": true,
       "site": "Miami Station" }
     -> { scan_id, subnet, scanned_hosts, alive_hosts, device_count,
          snmp_identified, devices[], connections[] }
```

Each device: `{ ip, open_ports, hostname, vendor, model, device_type,
confidence, snmp_community }`.

### Test

```bash
npm test            # pytest: mock SNMP agent, classifier, scanner, API
```

The SNMP client is validated against a live net-snmp `snmpd` as well as the
mock agent.

## Sprint 2 — Inventory Database (current)

SQLAlchemy ORM written for PostgreSQL with a SQLite local fallback. Discovery
results are persisted with last-seen tracking; inventory reports aggregate
the database.

```
backend/
  database.py     engine/session, DATABASE_URL config (sqlite default, postgres-ready)
  models.py       Device, ScanJob, Credential, Site
  repositories.py upsert_device (keyed on IP), scan job lifecycle, queries
  tests/          45 tests total (in-memory DB isolation)
```

- **Devices** keyed on `ip` (unique); re-discovery updates `last_seen`/fields
  and preserves `first_seen`.
- **ScanJobs** record subnet, communities, status, host/device counts, timestamps.
- **Credentials** (plaintext for now; encrypted in Sprint 3) and **Sites**.

### PostgreSQL

Switch engines with one env var — no code changes:

```bash
DATABASE_URL="postgresql+psycopg://user:pass@host:5432/network_mapper" npm run api
```

### API (new)

```
GET /api/inventory/devices            ?device_type=&vendor=&site=&limit=
GET /api/inventory/devices/{id}
GET /api/inventory/scans
GET /api/inventory/report             totals + counts by type/vendor/site
GET /api/inventory/credentials
GET /api/inventory/sites
```

## Roadmap

- **Sprint 1** Discovery + classification MVP ✅
- **Sprint 2** PostgreSQL inventory (Devices, ScanJobs, Credentials) ✅
- **Sprint 3** Encrypted credentials, SNMPv3, RBAC
- **Sprint 3** Encrypted credentials, SNMPv3, RBAC
- **Sprint 4** Interface discovery (SNMP/SSH)
- **Sprint 5** Topology collection (LLDP/CDP -> links)
- **Sprint 6** React Flow visualization
- **Sprint 7** VeloCloud Orchestrator + Cisco vManage integration
- **Sprint 8** sysObjectID database for advanced identification
- **Sprint 9** Configuration collection
- **Sprint 10** Layer 3 path analysis
- **Sprint 11** Change detection
- **Sprint 12** Reporting
- **Sprint 13** Redis/Celery scale-out
- **Sprint 14** Security hardening
- **Sprint 15** Production release

## Legacy files

`agent.js`, `catalyst-agent.js`, `worker/` and the Cloudflare deploy scripts
are legacy artifacts from the previous Node.js version and are not part of
the current build.

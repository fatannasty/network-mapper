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

## Sprint 1 — Discovery and Classification MVP ✅

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

## Sprint 3 — Encrypted Credentials, SNMPv3, RBAC ✅

Network credentials are encrypted at rest (Fernet), SNMPv3/USM discovery works
against real agents (AES-CFB128, DES-CBC, SHA-1/MD5 auth, no-privacy), and the
API is protected with role-based access control.

```
backend/
  security.py      Fernet key mgmt + AES-128 (scopedPDU, RFC 3826 CFB128), DES-CBC (RFC 3414)
  snmpv3.py        Pure-Python SNMPv3/USM client: engine discovery, key
                   localization, HMAC auth, AES/DES privacy (RFC 3414/3826)
  models.py        User model + EncryptedString(TypeDecorator) at-rest columns
  repositories.py  credential CRUD (encrypted), user CRUD + issue/verify token
  tests/           88 tests total (crypto, SNMPv3 vectors, auth, credentials)
```

- **Credentials** stored with a `enc:v1:` Fernet blob; `to_dict()` never leaks secrets.
- **SNMPv3**: engine discovery (empty-engineID report), RFC 3414 key localization
  (MD5/SHA), 12-byte HMAC truncation, AES-128-CFB (RFC 3826, no padding) and
  DES-CBC (RFC 3414) privacy. Validated live against net-snmp `snmpd` with
  SHA/authNoPriv, SHA/AES, and SHA/DES users, plus the official RFC test vectors.
- **RBAC**: `/api/auth/login` (scrypt-hashed passwords) issues HMAC-signed bearer
  tokens with `admin` / `operator` / `viewer` roles; `operator` can discover,
  `admin` manages users/credentials/sites, `viewer` reads inventory.
- **Encryption key**: `ENCRYPTION_KEY` env var, or auto-generated `backend/.secret_key`
  (gitignored, chmod 600).

### API (new / changed)

```
POST /api/auth/login                 { "username", "password" } -> { token, role }
GET  /api/auth/me                    current user
GET/POST/DELETE /api/auth/users      admin: user lifecycle
POST /api/discover                   operator: add "snmpv3": { username, auth_protocol,
                                     auth_password, privacy_protocol, privacy_password }
POST/DELETE /api/inventory/credentials   admin
POST /api/inventory/sites            admin
```

### Run it

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --reload
# login: .venv/bin/python -c "from repositories import create_user; create_user(db,'admin','change-me','admin')"
```

## Sprint 4 — Interface Discovery ✅

SNMP GETNEXT/GETBULK walks of the IF-MIB (`ifTable` + `ifXTable`) discover per-
device interfaces, persisted alongside each device and returned by the API.

```
backend/
  snmpv3.py        PDU_GETNEXT/PDU_GETBULK, snmpv3_getnext, snmpv3_walk,
                   walk_if_table (ifTable 1.3.6.1.2.1.2.2, ifXTable 1.3.6.1.2.1.31.1.1)
  scanner.py       snmpv3_interfaces() -> device["interfaces"] in identify_host
  models.py        Interface model (device_id FK, cascade delete-orphan)
  repositories.py  upsert_device syncs interface rows on each rescan
  tests/           98 tests total (GETNEXT/GETBULK mock agent, walk, persistence)
```

- **GETBULK walks** (`snmpv3_walk`) loop until the subtree is exhausted
  (`max_repetitions=20`, `max_oids=1024` cap); GETNEXT is used as the fallback
  primitive and for out-of-subtree termination.
- **Per-interface data**: ifIndex, ifDescr, ifName, ifType (mapped to names),
  ifSpeed/ifHighSpeed, ifPhysAddress (raw MAC bytes → `aa:bb:cc:dd:ee:ff`),
  ifAdminStatus/ifOperStatus, ifAlias.
- **Mock USM agent** extended to an in-memory MIB with a 2-interface
  ifTable/ifXTable and correct GET / GETNEXT / GETBULK response encoding
  (including OID-typed sysObjectID values).
- **Decoding fix**: `_parse_value` keeps OCTET STRING as raw bytes (lossless for
  MACs), Gauge32/Counter32/Counter64 are integers, and string call sites decode
  explicitly; verified live against net-snmp `snmpd` (25 interfaces on macOS).

### Device payload (new field)

Each discovered device now includes:

```
"interfaces": [
  { "ifIndex": "1", "ifDescr": "eth0", "ifName": "eth0", "ifType": "ethernet",
    "ifSpeed": "100000000", "ifPhysAddress": "00:11:22:33:44:55",
    "ifAdminStatus": "up", "ifOperStatus": "up",
    "ifHighSpeed": "100", "ifAlias": "" },
  ...
]
```

## Sprint 5 — Topology Collection (current) ✅

LLDP-MIB (IEEE 802.1AB) and Cisco CDP-MIB walks discover neighbor relationships,
which are parsed into per-device neighbor lists and turned into deduplicated
bidirectional topology links.

```
backend/
  topology.py      LLDP/CDP MIB constants, OID-oriented varbind parsers,
                   v2c/v3 collectors, canonical link builder (build_links)
  snmp.py          snmp_walk — v2c GETBULK loop, build_getbulk_request
  scanner.py       collect_topology (parallel LLDP+CDP on snmp_identified
                   devices), discover wires neighbors + connections
  models.py        Link model (endpoint_a/b, interface_a/b, protocol)
  repositories.py  replace_links / list_links
  main.py          replace_links in api_discover, GET /api/topology endpoint
  tests/           116 tests total (v2c GETBULK mock agent, parser/link
                   builder, v2c/v3 collection, scanner wiring, link
                   persistence, integration end-to-end, API topology)
```

- **LLDP remote table** (`1.0.8802.1.1.2.1.4.1.1.<col>.<time>.<port>.<rem>`):
  chassis ID (hex MAC), port ID/desc, system name, system desc.
- **CDP cache** (`1.3.6.1.4.1.9.9.23.1.2.1.1.<col>.<ifIndex>.<devIndex>`):
  address (raw IPv4 → dotted-decimal), device ID, device port, platform.
- **Link deduplication**: bidirectional LLDP/CDP reports of the same physical
  link collapse into a single entry with sorted endpoint keys and per-endpoint
  interface/hostname fields.
- **Mock v2c agent** extended with GET and GETBULK support against an
  in-memory MIB that includes LLDP/CDP entries (11 OIDs), plus the existing
  MockV3Agent extended to the same MIB entries for SNMPv3 topology testing.

### API (new)

```
GET  /api/topology?scan_id=  -> { scan_id, nodes[], links[] }
```

Nodes include discovered devices (by `last_scan_id`) plus unknown endpoint
entries for targets not in the current scan (e.g. unmanaged switches
reported via CDP).

Each link: `{ source, target, source_interface, target_interface, protocol,
source_hostname, target_hostname }`.

## Sprint 6 — React Flow Topology Visualization ✅

Vite + React + TypeScript frontend with React Flow canvas for interactive
network topology graphing, deployed to Cloudflare Pages.

```
frontend/
  src/
    api.ts                  Axios client with auth interceptor, all API calls
    App.tsx                 Router + auth state (login gating)
    components/
      LoginForm.tsx         Credentials -> POST /api/auth/login
      Layout.tsx            Nav bar (Topology, Discover) + logout
      DiscoveryForm.tsx     Subnet/community/SNMPv3 form -> POST /api/discover
      TopologyViewer.tsx    React Flow canvas: nodes (devices), edges (links),
                            custom DeviceNode, device detail sidebar
      DeviceNode.tsx        Custom node: hostname, vendor, model, type-colored
      DeviceDetail.tsx      Sidebar: IP, vendor, model, interfaces, open ports
  vite.config.ts            Tailwind CSS plugin + /api proxy to localhost:8000
```

- **React Flow** with custom device nodes (color-coded by type: switch blue,
  router amber, firewall red, core-switch purple), smooth-step links (CDP
  amber, LLDP blue), animated edges, minimap, controls, and background grid.
- **Layout algorithm**: depth-first traversal for tree-like topologies.
- **Device detail sidebar**: click any node to see IP, vendor, model, type,
  SNMP status, open ports, and all interfaces with status/speed/MAC.
- **Auth**: JWT bearer token stored in localStorage, auto-redirects to login
  on 401.
- **Proxy**: Vite dev server proxies `/api/*` to the FastAPI backend on
  port 8000 for zero-config local development.

### Run it

```bash
npm run api              # backend on :8000
npm run frontend:dev     # frontend on :5173 (proxies /api -> :8000)
npm run frontend:build   # production build -> frontend/dist/
```

## Sprint 2 — Inventory Database ✅

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
- **Credentials** (encrypted at rest since Sprint 3) and **Sites**.

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

## Sprint 12 — Reporting ✅

Full reporting on top of the inventory database: a Reports page aggregating
devices, topology links, interfaces, config-collection coverage and scan
history, with CSV export for each report.

- **Extended `/api/inventory/report`**: `total_devices`, `total_links`,
  `total_interfaces`, counts by device type / vendor / site, link protocol
  breakdown (LLDP/CDP), interface operational-status counts, config coverage
  (total configs, distinct devices, per-type), stale-device count (90 days),
  and full scan history with per-scan link counts.
- **CSV export** `GET /api/inventory/report/export?report=devices|links|scans|configs`
  returns a downloadable `text/csv` attachment for each report.
- **Reports page** (`frontend/src/components/Reports.tsx`): summary cards,
  distribution tables with bars, interface-status strip, config coverage by
  type, scan history table, and one-click CSV export buttons.
- Repository helpers in `repositories.py`: `count_links`, `count_interfaces`,
  `link_counts_by_protocol`, `interface_status_counts`, `config_coverage`,
  `scan_history`, `stale_devices`.

### API (new)

```
GET /api/inventory/report/export?report=devices|links|scans|configs   -> CSV download
```

## Roadmap

- **Sprint 1** Discovery + classification MVP ✅
- **Sprint 2** PostgreSQL inventory (Devices, ScanJobs, Credentials) ✅
- **Sprint 3** Encrypted credentials, SNMPv3, RBAC ✅
- **Sprint 4** Interface discovery (SNMP GETBULK walks) ✅
- **Sprint 5** Topology collection (LLDP/CDP -> links) ✅
- **Sprint 6** React Flow visualization ✅
- **Sprint 7** VeloCloud Orchestrator + Cisco vManage integration
- **Sprint 8** sysObjectID database for advanced identification
- **Sprint 9** Configuration collection
- **Sprint 10** Layer 3 path analysis
- **Sprint 11** Change detection ✅
- **Sprint 12** Reporting ✅
- **Sprint 13** Redis/Celery scale-out
- **Sprint 14** Security hardening
- **Sprint 15** Production release

## Legacy files

`agent.js`, `catalyst-agent.js`, `worker/` and the Cloudflare deploy scripts
are legacy artifacts from the previous Node.js version and are not part of
the current build.

# Network Mapper — Presentation Walkthrough Guide

High-level talking points for the Thursday review. Walk the app page-by-page
(the "Demo" lines tell you what to click), and use the bullets to summarize
progress and achievements. Keep it at this altitude — engineers can drill
into `VALIDATION.md` / `UBUNTU-DEPLOY.md` afterward if asked.

---

## 0. Opening — What we built (30 seconds)

- A **network mapping & health platform** for Amtrak's LAN/WAN: import the
  network, see it as an interactive map, monitor health, and export
  management-ready reports.
- **One source of truth** for 3,900+ devices, 20,000+ interfaces, and 42,000+
  links across 350+ sites.
- **For every audience:** guided onboarding for beginners, deep tooling for
  engineers, and an executive scorecard + scheduled reports for leadership.
- Security by design: RBAC roles, encrypted credential vault, hashed tokens.

**Demo:** Log in → land on Topology.

---

## 1. Dashboard — health at a glance

**Demo:** Dashboard → toggle **Operations / Executive**.

- **Executive view:** a single health score (0–100), overall state banner, and a
  drillable KPI scorecard (devices up, down, flapping, SPOF, coverage).
- **Site freshness** table shows each site, its device counts, and how recently
  data was collected — spot stale sites instantly.
- **Health trend** chart shows the score over the last 30 days (hourly recorder).
- **Busiest links** panel lists the top interfaces by traffic.
- **Operations view:** live outage/health signals, interface status, scan history.
- **Notifications bell** surfaces flapping / down / SPOF alerts with a "run check"
  button; alerts email out when SMTP is configured.

---

## 2. Topology — the interactive map

**Demo:** Topology → Simple vs **Technical** view; hover badges; site selector.

- Interactive diagram of the full network with **pan/zoom, focus-on-device, and
  path tracing** between two devices.
- **Health badges on every node:** status dot (up/degraded/down/flapping/unknown),
  amber **SPOF** (single point of failure), teal **VLAN 90** marker.
- Layouts: Tree / Radial / Circle / Free; **Simple → By Type / By Subnet** views
  collapse thousands of nodes into readable blocks.
- **VeloCloud SD-WAN edges** are now part of the map (fuchsia), showing their
  physical LAN connections — while WAN/backhaul overlay tunnels stay hidden.
- Performs smoothly at 3,900+ nodes (viewport culling, backend caching).

---

## 3. Inventory — device management

**Demo:** Inventory → search, filters, VLAN 90 toggle, select devices → bulk bar.

- Searchable, filterable device list (hostname/IP/type/site/**VLAN 90**).
- **Device detail panel:** interfaces with VLAN chips, status, latency, Catalyst
  ID, **config history + diff viewer**, and **link utilization charts**.
- **Bulk operations:** multi-select any devices → collect configs, walk
  interfaces, walk links, or assign a site in one click.
- Config-change detection: the two newest configs are diffed network-wide and
  surfaced in Data Quality.

---

## 4. Import — bring the network in

**Demo:** Import → **Discover**, **SNMP Walk**, **Catalyst**, **Meraki**, **VeloCloud**.

- **Discover:** SNMP subnet scans (v2c or **v3**) with device classification.
- **SNMP Walk:** bulk-walk interfaces + VLANs and LLDP/CDP links across a single
  site or the **whole network**, using vaulted communities or **SNMPv3**.
- **Catalyst:** Cisco Catalyst Center import (site-scoped or full environment),
  with **VLAN 90 detection** that stays consistent across full re-imports.
- **Meraki / VeloCloud:** dashboard-driven imports (VeloCloud SD-WAN edges).
- After import: export clean **Walk Reports** (interfaces/VLANs + links CSV) from
  the Topology page.

---

## 5. Data Quality & Admin — trust the data

**Demo:** Admin → Data Quality (backfill jobs, vault, site mappings, config changes).

- **Credential Vault:** SNMP/SSH creds encrypted at rest (Fernet) for background jobs.
- **Backfill jobs:** interface walks, LLDP/CDP link validation, blank-type
  classification — with per-device results.
- **Site mappings:** auto-discover hostname→site rules; backfill blank-site devices.
- **Recent config changes:** network-wide compliance view of config drift.
- **DoD gates** track coverage targets (site, interfaces, links, configs).
- **API Tokens:** create/revoke long-lived bearer tokens for automation.

---

## 6. Reporting & Automation — decisions, not diagrams

**Demo:** Dashboard → Executive → **Executive reports** → Open/PDF/Delete; Generate now.

- **Executive report (HTML + PDF)** with charts: status donut, coverage-vs-target
  bars, health trend line, busiest links — plus site/risk/SPOF tables.
- **Scheduled reports:** daily/weekly auto-generation; **emailed** as a PDF
  attachment when SMTP is configured.
- **Alerts** (flapping / down / SPOF) raise in-app notifications and email.
- **Automation backbone:** API tokens, nightly config backups, scheduled
  utilization sampling, hourly health history.

---

## 7. Engineering & quality — how it holds up

- **Architecture:** FastAPI + React, SQLite (file/Postgres-ready), Docker Compose,
  nginx-fronted SPA. Deploys via `UBUNTU-DEPLOY.md`; validated via `VALIDATION.md`.
- **Security:** RBAC (viewer/operator/admin), scrypt password hashing, Fernet
  encrypted secrets, API tokens hashed at rest, login rate limiting.
- **Performance:** responsive at 3,900+ devices via viewport culling and a
  topology TTL cache; background pollers keep data fresh (latency, utilization,
  alerts, configs, health history).
- **Testing:** **236 backend tests** + **7 Playwright end-to-end tests**, CI on
  GitHub Actions, lint + type-safe build.
- **Audience features:** first-run onboarding tour + plain-language glossary,
  Simple/Technical views, executive vs operations dashboards.

---

## Suggested pacing (45 min)

| Time | Section |
|------|---------|
| 0:00 | Opening — what we built |
| 0:05 | Dashboard (Executive + Operations) |
| 0:12 | Topology (badges, SPOF, VLAN 90, VeloCloud, cluster views) |
| 0:20 | Inventory (filters, bulk ops, config diff, utilization) |
| 0:27 | Import (SNMP Walk v3, Catalyst, VeloCloud) |
| 0:34 | Data Quality & Admin (vault, backfills, API tokens) |
| 0:40 | Reporting & automation (exec reports, alerts) |
| 0:44 | Engineering & quality + Q&A |
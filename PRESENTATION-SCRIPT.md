# Network Mapper — Presentation Script (verbatim)

Rehearse this click-by-click. **[CLICK]** = action. *"Text"* = what to say.
Timing in parentheses. Optional deeper lines marked **(deep)** for technical reviewers.

Setup before starting: open the app (http://localhost:5173), log in as admin,
keep a fresh **Executive report** generated (Dashboard → Executive → Reports →
Generate now) so it's in the archive.

---

## 0. Opening (1 min)

**[CLICK]** Show `EXEC-SUMMARY.html` (project it or a PDF of it).

*"Good morning. We set out to build one platform that can see, monitor, and
report on the Amtrak network. That's what this is. It maps 3,900-plus devices,
20,000-plus interfaces, 42,000-plus links across 350-plus sites — from Catalyst,
SNMP, Meraki, and VeloCloud SD-WAN — in one interactive view."*

**[CLICK]** Switch to the browser (already logged in, on Topology).

---

## 1. Dashboard — Executive (4 min)

**[CLICK]** Sidebar → **Dashboard**.

*"Let's start with the answer, not the mechanics. The Executive view is a
management scorecard — one number: the health score."*

**[CLICK]** Toggle **Executive** (top-right, if not already).

*"The score combines uptime with how complete our data is."*

**[CLICK]** Point to the score ring and the state banner.

*"Down devices, flapping links, and single points of failure are called out
directly. Every card is clickable — this is drill-down, not just a chart."*

**[CLICK]** Click **SPOF** card → lands in Topology showing SPOF badges.

*"From scorecard to the actual device in one click."*

**[CLICK]** Back to Dashboard → **Executive**.

*"Site freshness shows us every location and how recently we've collected data —
so we know where our picture is current and where it isn't."*

**[CLICK]** Scroll to **Site freshness** table; then **Health trend**; then **Busiest links**.

*"The health trend is the score over time — we record it hourly. Busiest links
shows the interfaces carrying the most traffic."*

**[CLICK]** Toggle **Operations** briefly.

*"For engineers there's the live Operations view — interface status, scan
history, outage signals."*

**[CLICK]** Toggle back to **Executive**.

---

## 2. Topology (8 min) — the centerpiece

**[CLICK]** Sidebar → **Topology**. Set the view to **Technical**.

*"This is the network as a diagram. Every device is an icon, colored by type;
lines are physical links."*

**[CLICK]** Hover / point to a node's badges (top-right status dot; top-left SPOF ⚠; teal V90).

*"Each node carries health badges: the status dot — up, degraded, down,
flapping — the amber warning is a single point of failure, and teal marks the
switches carrying VLAN 90."*

**[CLICK]** Select a site from the **site dropdown** (e.g., **Wilmington**).

*"Let's look at a real site. Here's Wilmington — the fuchsia node is the
VeloCloud SD-WAN edge, connected to its core switch and the LAN. Notice there
are no phantom links across the country — those were WAN overlay tunnels, and
we deliberately keep them off the physical map."*

**[CLICK]** Pick a **small site** from the dropdown (e.g., a site with just an edge + switch).

*"And a small site — here the edge connects directly to an access switch with
no core in between. That's the honest, real-world topology."*

**[CLICK]** Set view back to the **full environment** (site = all); switch to **Simple → By Subnet**.

*"At this scale — nearly four thousand devices — the Simple view collapses
everything into readable blocks by subnet or type."*

**(deep)** *"Layouts are computed in milliseconds — no force simulation — and
the renderer only draws what's on screen, so it stays smooth."*

**[CLICK]** (optional) Demo **path tracing**: set a source and target device, click **Find path**.

*"We can trace the path between any two devices — useful for troubleshooting."*

---

## 3. Inventory (4 min)

**[CLICK]** Sidebar → **Inventory**.

*"Every device lives here — searchable and filterable."*

**[CLICK]** Click the **VLAN 90** filter (All → VLAN 90).

*"We can filter to just the switches carrying VLAN 90 — 428 of them — flagged
consistently even after full re-imports."*

**[CLICK]** Click a device card to open the **detail panel**.

*"The detail panel is where the depth shows: interfaces with their VLANs, the
config history with a color-coded diff between any two backups, and live link
utilization charts."*

**[CLICK]** Expand **Config history** → pick two configs → show the diff.
**[CLICK]** Scroll to **Link utilization** → point at the in/out chart.

*"Config diffs give us change detection for compliance. Utilization shows how
links are actually being used."*

**[CLICK]** Close detail. Select a few devices (checkboxes) → **bulk bar** appears.

*"And bulk operations: select any set of devices and collect configs, walk
interfaces, walk links, or assign a site — in one click."*

**[CLICK]** (optional) Click **Assign site** to show the prompt, then Cancel.

---

## 4. Import (4 min)

**[CLICK]** Sidebar → **Import**.

*"This is how data gets in — five sources."*

**[CLICK]** Click the **SNMP Walk** tab.

*"The SNMP Walk is our workhorse: walk interfaces, VLANs, and links across a
single site or the whole network, using SNMPv3 — with proper authentication
and encryption, no external daemons."*

**[CLICK]** Point at the scope dropdown and the v3 toggle.

**[CLICK]** Click the **Catalyst** tab.

*"Catalyst imports from Cisco Catalyst Center — site-scoped or the full
environment. And crucially, VLAN 90 flags are recomputed after every full
import, so a re-import never loses them."*

**[CLICK]** Click the **VeloCloud** tab.

*"VeloCloud brings in the SD-WAN edges — the fuchsia nodes you saw on the map."*

---

## 5. Data Quality & Admin (3 min)

**[CLICK]** Sidebar → **Admin** → **Data Quality**.

*"Trusting the data is everything, so we give it teeth."*

**[CLICK]** Point to **Credential Vault**, **Backfill jobs**, **Recent config changes**.

*"Credentials are encrypted at rest. Backfill jobs repair data automatically.
Recent config changes is a network-wide compliance view of config drift."*

**[CLICK]** Scroll to **API Tokens**.

*"And for automation, long-lived API tokens — hashed, revocable, role-scoped —
so scripts can drive the platform securely."*

---

## 6. Reports & automation (3 min)

**[CLICK]** Dashboard → **Executive** → **Executive reports** (scroll to the Reports card).

*"And the payoff for leadership: one-click executive reports."*

**[CLICK]** Click **Open** on a report (or **Generate now** first) → opens the styled HTML.

*"Every report has a health score, charts — composition, coverage vs targets,
the trend — plus site freshness, risks, and SPOF."*

**[CLICK]** Download the **PDF** version (or open the PDF link).

*"A print-ready PDF with the same charts, generated and emailed on a schedule
— daily or weekly — so leadership gets this without asking."*

**(deep)** *"Each chart is isolated so a data hiccup can't break the report."*

---

## 7. Engineering & quality (2 min)

*"Under the hood it's FastAPI and React, packaged in Docker. Security is built
in — role-based access, an encrypted credential vault, hashed API tokens.
It's tested: 236 backend tests and 7 end-to-end browser tests, running in CI
on every change. And it performs — we cut the inventory payload sixfold —
down to under a quarter second — without changing a thing the users see."*

*"For the engineers in the room, the full technical deep dive is in the repo."*

**[CLICK]** (optional) Show `PRESENTATION-TECH.md` on screen.

---

## 8. Q&A

*"Happy to go deeper on any of it. We've also got a validated deployment guide
and a launch validation checklist ready to go."*

---

## Rehearsal tips
- The **Exec report** must exist before you start (Generate now if it doesn't).
- Wilmington site name: **"405 N King Street, Wilmington"**; for a small site
  pick one with a single edge + switch (check the site dropdown for a 2-device site).
- If a page is slow on first load, say: *"first load builds the cache — watch
  how fast it is the second time."*
- Keep the fuchsia = VeloCloud, teal = VLAN 90, amber = SPOF framing consistent —
  it's your visual story.
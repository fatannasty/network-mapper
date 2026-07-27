# Network Topology Mapper

A web-based network topology diagram tool with **automatic network discovery**. Scans your real network, identifies devices, and visualizes the topology.

## Features

- **Auto-scan** - discovers devices on your real network via ARP, ping sweep, and port scanning
- **Device identification** - detects routers, switches, access points, firewalls, servers, PCs
- **Proper icons** - realistic network device icons on canvas
- **VLAN display** - show uplink/downlink VLANs on connection lines
- **Open ports** - display discovered ports on each device
- **Drag & drop** - manually add and position network devices
- **Connect devices** - draw links between devices with labels
- **Device properties** - name, IP, MAC, vendor, type, open ports, notes
- **Demo mode** - generate a sample topology without scanning
- **Save/Load** - export/import topologies as JSON
- **Auto Layout** - arrange devices in a circle
- **Real-time updates** - WebSocket for live scan progress

## Live Demo

**https://networkmapper.5cloudmedia.com** (demo mode, no scanning)

## Quick Start (Demo Mode)

Open `index.html` in any browser. Click **Demo** to see a sample topology.

## Full Setup (Real Network Scanning)

```bash
npm install
npm start
```

Open **http://localhost:7777** and click **Scan Network**.

> **Note:** Network scanning requires the app to run locally. The scanner reads your ARP table and pings your subnet.

## Deployment

### Cloudflare Pages (Frontend)

```bash
npm run deploy
```

Frontend is always available at: **https://networkmapper-5cloudmedia.pages.dev**

### Cloudflare Tunnel (For Scanning)

```bash
npm run setup-tunnel  # One-time setup
npm start             # Start server
npm run tunnel        # Start tunnel (in separate terminal)
```

Custom domain: **https://networkmapper.5cloudmedia.com**

### Auto Push to GitHub

```bash
npm run watch  # Watches for changes and auto-commits/pushes
```

## File Structure

```
network-mapper/
  index.html           - Main HTML page
  style.css            - Styles (dark theme)
  app.js               - Frontend application logic
  server.js            - Express server with scan API
  scanner.js           - Network scanning engine
  package.json         - Node.js dependencies
  deploy.sh            - Cloudflare Pages deploy script
  auto-push.sh         - Auto-commit/push watcher
  setup-tunnel.sh      - Cloudflare Tunnel setup
  cloudflared-config.yml - Tunnel configuration
```

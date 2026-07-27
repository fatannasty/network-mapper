# Network Topology Mapper

A web-based network topology diagram tool with **automatic network discovery**. Scans your real network, identifies devices, and visualizes the topology.

## Features

- **Auto-scan** - discovers devices on your real network via ARP, ping sweep, and port scanning
- **Device identification** - detects routers, switches, access points, firewalls, servers, PCs
- **Drag & drop** - manually add and position network devices
- **Connect devices** - draw links between devices with labels
- **Device properties** - name, IP, MAC, vendor, type, open ports, notes
- **Demo mode** - generate a sample topology without scanning
- **Save/Load** - export/import topologies as JSON
- **Auto Layout** - arrange devices in a circle
- **Real-time updates** - WebSocket for live scan progress

## Quick Start (Demo Mode)

Open `index.html` in any browser. Click **Demo** to see a sample topology.

## Full Setup (Real Network Scanning)

```bash
# Install dependencies
npm install

# Start the server
npm start

# Open in browser
open http://localhost:3000
```

Click **Scan Network** to discover devices on your local network.

> **Note:** Network scanning requires the app to be run locally (not hosted remotely). The scanner reads your ARP table and pings your subnet.

## How Scanning Works

1. **ARP table** - reads already-known devices from your OS
2. **Ping sweep** - pings all 254 IPs in your subnet to find alive hosts
3. **Port scan** - checks common ports (22, 23, 80, 443, 161, etc.) to identify device types
4. **Vendor lookup** - matches MAC address prefixes to manufacturers
5. **Topology builder** - creates connections based on device types and network hierarchy

## File Structure

```
network-mapper/
  index.html   - Main HTML page
  style.css    - Styles (dark theme)
  app.js       - Frontend application logic
  server.js    - Express server with scan API
  scanner.js   - Network scanning engine
  package.json - Node.js dependencies
```

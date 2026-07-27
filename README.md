# Network Topology Mapper

A web-based network topology diagram tool with **automatic network discovery**. Scans your real network, identifies devices, and visualizes the topology.

## Features

- **Auto-scan** - discovers devices on your real network via ARP, ping sweep, and port scanning
- **Device identification** - detects routers, switches (Core/Access), access points, firewalls, servers, PCs
- **Cisco icons** - professional Cisco-style SVG icons for all device types
- **Hierarchical diagrams** - Core Switch → Access Switch topology layout
- **Cable types** - color-coded connections (Fiber, Cat6, Cat6a, DAC)
- **Port labels** - show port connections (e.g. GI1/0/1 ↔ TE1/1/1)
- **VLAN display** - show uplink/downlink VLANs on connection lines
- **Location tracking** - geographic site information per device
- **Drag & drop** - manually add and position network devices
- **Device properties** - hostname, IP, model, location, open ports, notes
- **Demo mode** - generate a sample topology without scanning
- **Save/Load** - export/import topologies as JSON
- **Auto Layout** - arrange devices in a circle
- **Catalyst Center** - integration with Cisco DNA Center
- **Multi-site** - scanner agents for multiple locations

## Live Demo

**https://networkmapper-5cloudmedia.pages.dev** (demo mode, no scanning)

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/fatannasty/network-mapper.git
cd network-mapper
docker compose up -d --build
```

Open **http://localhost:7777**

### Option 2: Node.js

```bash
git clone https://github.com/fatannasty/network-mapper.git
cd network-mapper
npm install
npm start
```

Open **http://localhost:7777**

### Option 3: Direct

Open `index.html` in any browser. Click **Demo** to see a sample topology.

## Docker Deployment

### Single Server

```bash
# Clone and run
git clone https://github.com/fatannasty/network-mapper.git
cd network-mapper
docker compose up -d --build

# Check status
docker logs -f network-mapper

# Stop
docker compose down

# Restart
docker compose restart
```

### Multi-Site Deployment (Ubuntu)

Deploy one container at each switch location:

**On each Ubuntu server:**

```bash
# Install Docker (one-time)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Clone and run
git clone https://github.com/fatannasty/network-mapper.git
cd network-mapper
docker compose up -d --build
```

**Access each site:**

| Location | Server | URL |
|----------|--------|-----|
| Site A | 10.1.1.10 | http://10.1.1.10:7777 |
| Site B | 10.2.1.10 | http://10.2.1.10:7777 |
| Site C | 10.3.1.10 | http://10.3.1.10:7777 |

### Docker with Custom Port

```yaml
# docker-compose.yml
services:
  network-mapper:
    build: .
    ports:
      - "8080:7777"
    restart: unless-stopped
```

### Docker with Host Networking (Recommended for Scanning)

```yaml
services:
  network-mapper:
    build: .
    network_mode: host
    restart: unless-stopped
```

## Deployment Options

### Cloudflare Pages (Frontend Only)

```bash
npm run deploy
```

Frontend always available at: **https://networkmapper-5cloudmedia.pages.dev**

### Cloudflare Tunnel (Remote Scanning)

```bash
npm run setup-tunnel  # One-time setup
npm start             # Start server
npm run tunnel        # Start tunnel
```

Custom domain: **https://networkmapper.5cloudmedia.com**

### Scanner Agent (Multi-Site)

```bash
# At each location with VPN access
LOCATION_ID=miami LOCATION_NAME="Miami Station" node agent.js
```

Or with Docker:

```bash
docker compose -f docker-compose.agent.yml up -d
```

## Catalyst Center Integration

1. Open the web UI
2. Enter Cat Center URL, username, and password in the sidebar
3. Click **Test Connection** to verify
4. Click **Scan via Cat Center** to import all devices and topology

## Commands Reference

| Command | Description |
|---------|-------------|
| `npm start` | Start local server |
| `npm run deploy` | Deploy to Cloudflare Pages |
| `npm run tunnel` | Start Cloudflare Tunnel |
| `npm run watch` | Auto-push to GitHub |
| `docker compose up -d` | Start Docker container |
| `docker compose down` | Stop Docker container |
| `docker compose logs -f` | View container logs |

## File Structure

```
network-mapper/
  index.html            - Main HTML page
  style.css             - Styles (modern dark theme)
  app.js                - Frontend application
  server.js             - Express server with scan API
  scanner.js            - Network scanning engine
  agent.js              - Multi-site scanner agent
  catalyst-agent.js     - Cisco Cat Center integration
  icons/                - Cisco-style SVG icons
  worker/               - Cloudflare Worker API
  Dockerfile            - Docker build file
  docker-compose.yml    - Docker Compose config
  docker-compose.agent.yml - Agent Docker config
```

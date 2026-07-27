# Network Topology Mapper - Ubuntu Deployment Guide

## Prerequisites

- Ubuntu 20.04+ server at each switch location
- Network access to the switches
- Outbound internet access (to push results to Cloudflare)

## Step 1: Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (logout/login after)
sudo usermod -aG docker $USER

# Verify
docker --version
```

## Step 2: Clone and Run

```bash
# Clone the repo
git clone https://github.com/fatannasty/network-mapper.git
cd network-mapper

# Build and start
docker compose up -d --build

# Verify it's running
docker logs network-mapper
```

## Step 3: Configure Network Access

The container uses `network_mode: host` to access the local network. Edit `docker-compose.yml` if needed:

```yaml
services:
  network-mapper:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: network-mapper
    network_mode: host
    restart: unless-stopped
    environment:
      - PORT=7777
```

## Step 4: Access the Web UI

Open in browser:
```
http://<server-ip>:7777
```

## Step 5: Scan the Local Network

1. Click **Scan Network** button
2. Or right-click to set a specific CIDR (e.g. `10.0.0.0/24`)

## Step 6: (Optional) Push Results to Cloudflare

If using the Cloudflare Worker for multi-site visibility, results auto-push when agents are configured.

## Step 7: (Optional) Run as System Service

```bash
# Enable auto-start on boot
sudo systemctl enable docker
sudo systemctl start docker
```

## Troubleshooting

### Container can't see network interfaces
```bash
# Check network interfaces
ip addr show

# Test ping from container
docker exec network-mapper ping -c 1 <switch-ip>
```

### Port 7777 already in use
```bash
# Change port in docker-compose.yml
ports:
  - "8080:7777"

# Or set environment variable
environment:
  - PORT=8080
```

### Permission denied errors
```bash
# The container needs raw socket access for ping
# Run with:
docker compose down
docker compose up -d --build
```

## Multi-Site Setup

Deploy one container at each location:

| Location | Server IP | Docker Port |
|----------|-----------|-------------|
| Miami Station | 10.1.1.10 | 7777 |
| Hialeah Yard | 10.2.1.10 | 7777 |
| Fort Lauderdale | 10.3.1.10 | 7777 |

Each container scans its local network independently.

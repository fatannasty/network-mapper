# Network Mapper — Ubuntu Deployment Guide

Production deployment guide for the network-mapper stack (FastAPI backend +
Vite/nginx frontend, SQLite with a persistent volume).

## Prerequisites

- Ubuntu 20.04+ server with network reachability to the switches you will scan.
- Docker + Docker Compose v2.
- A `SECRET_KEY` (and ideally `ENCRYPTION_KEY`) for token signing / at-rest encryption.

## Step 1: Install Docker

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER   # log out/in afterwards
docker --version
docker compose version
```

## Step 2: Clone and configure

```bash
git clone https://github.com/fatannasty/network-mapper.git
cd network-mapper

# Create a production environment file (gitignored) with your secrets.
cat > .env << 'EOF'
SECRET_KEY=$(openssl rand -base64 32)
ENCRYPTION_KEY=$(openssl rand -base64 32)

# Optional: scheduled executive reports (hourly | daily | weekly | off)
EXEC_REPORT_SCHEDULE=weekly

# Optional: email delivery (used by exec reports and alerts)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=reporter@example.com
SMTP_PASSWORD=changeme
SMTP_FROM=reporter@example.com
REPORT_TO=ops@example.com,leadership@example.com

# Optional tuning
LATENCY_POLL_INTERVAL=60
UTIL_POLL_INTERVAL=300
ALERT_CHECK_INTERVAL=300
EOF
```

## Step 3: Build and start

```bash
docker compose up -d --build
docker compose ps          # both services healthy
```

- Web UI: `http://<server-ip>:8080`  (nginx proxies `/api` to the backend)
- API:   `http://<server-ip>:8000`
- Health: `curl http://<server-ip>:8000/health`

The SQLite database lives in the `app-data` volume, so data and collected
configs survive rebuilds.

## Step 4: Create the first admin user

If the DB has no users yet, seed one inside the backend container:

```bash
docker compose exec backend python -c \
  "from database import SessionLocal; import repositories; db=SessionLocal(); repositories.create_user(db,'admin','change-me-now','admin'); db.close()"
```

Log in, then change the password immediately.

## Step 5: Bring your network in

1. **Import -> Discover** — scan a subnet with an SNMP community.
2. **Import -> SNMP Walk** — bulk-walk interfaces/VLANs/links across a whole
   site or the entire network (v2c vaulted or SNMPv3).
3. **Import -> Catalyst / Meraki / VeloCloud** — vendor dashboards.
4. **Inventory -> Collect Configs** — SSH config backups (needed for the VLAN 90
   flag and config-diff/change detection).

Store SNMP/SSH credentials in **Data Quality -> Credential Vault** so background
jobs (utilization, alerts, backfills) can use them.

## Step 6: Automation & reporting

- **Admin -> API Tokens** — create long-lived bearer tokens for scripts:
  `curl -H "Authorization: Bearer <token>" http://<server-ip>:8000/api/health/exec`
- **Dashboard -> Executive** — scorecard + busiest links + archived reports.
  Set `EXEC_REPORT_SCHEDULE` and SMTP env vars to auto-generate and email them.
- **Alerts** — flapping/down/SPOF notifications appear in the header bell and
  email out when SMTP is configured.

## Step 7: Enable auto-start on boot

```bash
sudo systemctl enable docker
docker update --restart unless-stopped network-mapper-api network-mapper-web
```

## Upgrading

```bash
git pull
docker compose up -d --build
```

## Troubleshooting

- **Healthcheck failing / API down:** `docker compose logs backend`
- **Frontend can't reach the API:** confirm the backend container is healthy and
  nginx proxies `/api` to `http://backend:8000`.
- **SNMP walks time out:** the container must reach the switches — verify
  routing/firewall, and that the community/v3 user is allowed.
- **No utilization/alerts:** those background jobs need vaulted SNMP communities
  (`Data Quality -> Credential Vault`) and are gated by `UTIL_POLL_INTERVAL` /
  `ALERT_CHECK_INTERVAL` (both default to 300s).
- **Ports already in use:** change the `ports:` mapping in `docker-compose.yml`.

## Multi-site

Deploy one instance per site (each with its own `app-data` volume), or run a
single instance and add sites via Catalyst / the SNMP Walk site scope.
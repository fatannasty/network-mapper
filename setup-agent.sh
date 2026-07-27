#!/bin/bash

echo "========================================="
echo "  Network Mapper - Cat Center Agent"
echo "========================================="
echo ""
echo "This agent runs in Docker and connects to"
echo "your Cat Center via VPN, then pushes"
echo "results to Cloudflare."
echo ""

read -p "Cat Center URL (e.g. https://catc.company.com): " CATC_URL
read -p "Cat Center Username: " CATC_USER
read -p "Cat Center Password: " CATC_PASS
read -p "Scan interval in seconds [300]: " INTERVAL
INTERVAL=${INTERVAL:-300}

cat > .env.agent << EOF
CAT_CENTER_URL=$CATC_URL
CAT_CENTER_USER=$CATC_USER
CAT_CENTER_PASS=$CATC_PASS
SCAN_INTERVAL=$((INTERVAL * 1000))
API_URL=https://network-mapper-api.fatannasty.workers.dev
EOF

echo ""
echo "Building and starting agent..."
echo ""

docker compose -f docker-compose.agent.yml --env-file .env.agent up -d --build

echo ""
echo "Agent started! Check logs with:"
echo "  docker logs -f network-mapper-agent"
echo ""
echo "Stop with:"
echo "  docker compose -f docker-compose.agent.yml down"
echo ""

#!/bin/bash

echo "========================================="
echo "  Network Mapper - Ubuntu Setup"
echo "========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
  echo "Docker not found. Installing..."
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  rm get-docker.sh
  sudo usermod -aG docker $USER
  echo ""
  echo "Docker installed! Please logout and login again, then re-run this script."
  exit 1
fi

echo "Docker found: $(docker --version)"
echo ""

# Clone repo if not present
if [ ! -f "docker-compose.yml" ]; then
  echo "Cloning Network Mapper..."
  git clone https://github.com/fatannasty/network-mapper.git
  cd network-mapper
fi

echo "Building and starting container..."
docker compose up -d --build

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "Web UI: http://$(hostname -I | awk '{print $1}'):7777"
echo ""
echo "Commands:"
echo "  docker logs -f network-mapper   # Watch logs"
echo "  docker compose down             # Stop"
echo "  docker compose up -d            # Start"
echo "  docker compose restart          # Restart"
echo ""

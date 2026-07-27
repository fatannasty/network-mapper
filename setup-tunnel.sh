#!/bin/bash

echo "========================================="
echo "  Cloudflare Tunnel Setup for"
echo "  networkmapper.5cloudmedia.com"
echo "========================================="
echo ""

TUNNEL_NAME="networkmapper"
DOMAIN="networkmapper.5cloudmedia.com"
CONFIG_FILE="$(dirname "$0")/cloudflared-config.yml"

# Check cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
  echo "Installing cloudflared..."
  brew install cloudflare/cloudflare/cloudflared
fi

echo "Step 1: Login to Cloudflare"
echo "  (A browser window will open - select 5cloudmedia.com)"
echo ""
cloudflared tunnel login
echo ""

echo "Step 2: Creating tunnel '$TUNNEL_NAME'..."
cloudflared tunnel create "$TUNNEL_NAME" 2>&1
echo ""

# Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

# Update config file with actual tunnel ID
if [ -n "$TUNNEL_ID" ]; then
  sed -i '' "s/<TUNNEL_ID>/$TUNNEL_ID/" "$CONFIG_FILE"
  echo "Updated config with tunnel ID"
fi
echo ""

echo "Step 3: Create DNS record for $DOMAIN..."
cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN" 2>&1
echo ""

echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "To start the tunnel, run:"
echo "  cloudflared tunnel --config $CONFIG_FILE run"
echo ""
echo "Or use the npm script:"
echo "  npm run tunnel"
echo ""
echo "Make sure your server is running:"
echo "  npm start"
echo ""
echo "Your app will be available at:"
echo "  https://$DOMAIN"
echo ""

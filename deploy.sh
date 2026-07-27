#!/bin/bash

echo "Deploying Network Mapper to Cloudflare Pages..."
echo ""

DEPLOY_DIR="/tmp/network-mapper-deploy"
PROJECT="networkmapper-5cloudmedia"

rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR/icons"

cp index.html style.css app.js "$DEPLOY_DIR/"
cp icons/*.svg "$DEPLOY_DIR/icons/"

npx wrangler pages deploy "$DEPLOY_DIR" --project-name="$PROJECT" --branch=main --commit-dirty=true 2>&1

echo ""
echo "Deployed! Check: https://$PROJECT.pages.dev"
echo "Custom domain: https://networkmapper.5cloudmedia.com"

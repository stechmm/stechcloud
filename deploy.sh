#!/bin/bash
# ==========================================================
# DigitalOcean VPS Auto-Deploy Script for S-Tech Cloud
# ==========================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🚀 Updating system packages..."
sudo apt update
sudo apt install -y docker.io python3 python3-pip python3-venv ufw

echo "🔧 Starting Docker service..."
sudo systemctl enable --now docker

echo "📁 Creating storage folders..."
mkdir -p storage data/trash storage/Telegram_Uploads

echo "🚀 Building and launching S-Tech Cloud container (Port 8090)..."
docker build -t stechcloud_personal-cloud:latest "$DIR"
docker rm -f personal-cloud-app 2>/dev/null || true

docker run -d \
  --name personal-cloud-app \
  --restart always \
  -p "8090:8090" \
  -e PORT="8090" \
  -e ADMIN_PASSWORD="admin123" \
  -e JWT_SECRET="$(openssl rand -hex 24)" \
  -v "$DIR/storage:/app/storage" \
  -v "$DIR/data:/app/data" \
  stechcloud_personal-cloud:latest

echo "✅ S-Tech Cloud Deployment complete!"
echo "🌐 You can now access your cloud at: http://$(curl -s ifconfig.me):8090"

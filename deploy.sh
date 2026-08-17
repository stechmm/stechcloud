#!/bin/bash
# ==========================================================
# DigitalOcean VPS Auto-Deploy Script for Personal Cloud
# ==========================================================

echo "🚀 Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "📦 Installing Docker & Docker Compose..."
sudo apt install -y docker.io docker-compose

echo "🔧 Starting Docker service..."
sudo systemctl enable --now docker

echo "📁 Creating storage folders..."
mkdir -p storage data/trash

echo "🚀 Building and launching Personal Cloud container..."
docker-compose up -d --build

echo "✅ Deployment complete!"
echo "🌐 You can now access your cloud at: http://$(curl -s ifconfig.me):3000"

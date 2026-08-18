#!/bin/bash
# ==============================================================================
# S-Tech Server Maintenance Agent - Auto Setup & Systemd Installer
# ==============================================================================

set -e

echo "📦 Installing Python3 & Virtualenv..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🐍 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f "config.env" ]; then
    echo "⚠️ config.env not found. Copying from config.env.example..."
    cp config.env.example config.env
    echo "❗ IMPORTANT: Please edit 'config.env' with your Telegram Bot Token & Chat ID!"
fi

echo "⚙️ Creating Systemd Service (stech-agent.service)..."
cat <<EOF | sudo tee /etc/systemd/system/stech-agent.service
[Unit]
Description=S-Tech VPS Server Maintenance AI Agent
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python3 $DIR/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Reloading systemd and enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable stech-agent.service

echo ""
echo "✅ Setup complete!"
echo "👉 Edit your config: nano $DIR/config.env"
echo "👉 Start agent:     sudo systemctl start stech-agent"
echo "👉 Check status:    sudo systemctl status stech-agent"
echo "👉 View logs:       sudo journalctl -u stech-agent -f"

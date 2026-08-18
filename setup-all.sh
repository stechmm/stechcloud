#!/bin/bash
# ==============================================================================
# 🚀 S-Tech All-in-One Master Deployment Suite (Cloud + AI DevOps Agent)
# Author: Antigravity
# Description: 1-Click Interactive setup for S-Tech Cloud Storage, Cyber Defense,
# and Telegram AI DevOps Brain Assistant on DigitalOcean / Ubuntu VPS.
# ==============================================================================

set -e

# ANSI Color Palette
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

clear
echo -e "${CYAN}"
echo "======================================================================"
echo "      🚀 S-TECH ALL-IN-ONE CLOUD & AI DEVOPS MASTER INSTALLER"
echo "======================================================================"
echo -e "${NC}"

# Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}❌ Please run as root (e.g. sudo bash setup-all.sh)${NC}"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$PROJECT_DIR"

echo -e "${YELLOW}📝 Please enter your configuration settings below:${NC}"
echo "----------------------------------------------------------------------"

# 1. Master Cloud Password
read -p "🔑 Enter Cloud Master Password [default: admin123]: " INPUT_PASSWORD
ADMIN_PASSWORD=${INPUT_PASSWORD:-admin123}

# 2. Telegram Bot Token
echo ""
echo -e "${CYAN}🤖 Telegram Bot Setup (from @BotFather):${NC}"
read -p "👉 Enter Telegram Bot Token (or press Enter to skip for now): " TG_BOT_TOKEN

# 3. Telegram Admin Chat ID
echo ""
echo -e "${CYAN}👤 Telegram Admin Numeric ID (from @userinfobot):${NC}"
read -p "👉 Enter Your Telegram Chat ID: " TG_CHAT_ID

# 4. Google Gemini API Key
echo ""
echo -e "${CYAN}🧠 Google Gemini AI Key (Free from https://aistudio.google.com/app/apikey):${NC}"
read -p "👉 Enter Gemini API Key (or press Enter to skip for now): " GEMINI_KEY

# 5. Optional Domain Name
echo ""
echo -e "${CYAN}🌐 Domain Name (Optional for HTTPS/SSL, e.g. cloud.yourdomain.com):${NC}"
read -p "👉 Enter Domain Name (leave blank to use VPS IP): " DOMAIN_NAME

echo "----------------------------------------------------------------------"
echo -e "${GREEN}⏳ Starting All-in-One Installation...${NC}"
echo "----------------------------------------------------------------------"

# Step 1: Update System & Install Core Tools
echo -e "${BLUE}📦 [1/6] Updating Ubuntu packages & installing dependencies...${NC}"
apt update && apt upgrade -y
apt install -y docker.io docker-compose python3 python3-pip python3-venv curl git ufw udev

systemctl enable --now docker

# Step 2: Configure Firewall & Cyber Shield
echo -e "${BLUE}🛡️ [2/6] Configuring UFW Firewall & Cyber Shield...${NC}"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw allow 3000/tcp    # S-Tech Cloud
ufw allow 51820/udp   # WireGuard VPN (if used)
echo "y" | ufw enable || true

# Step 3: Configure S-Tech Cloud
echo -e "${BLUE}☁️ [3/6] Setting up S-Tech Cloud Storage...${NC}"
mkdir -p "$PROJECT_DIR/storage" "$PROJECT_DIR/data/trash"

cat <<EOF > "$PROJECT_DIR/.env"
PORT=3000
ADMIN_PASSWORD=$ADMIN_PASSWORD
JWT_SECRET=$(openssl rand -hex 24)
EOF

# Build & Launch S-Tech Cloud Container
echo -e "${BLUE}🐳 [4/6] Launching S-Tech Cloud Docker Container...${NC}"
docker-compose up -d --build

# Step 4: Setup S-Tech AI DevOps Agent
echo -e "${BLUE}🤖 [5/6] Setting up AI DevOps & Cyber Defense Agent...${NC}"
AGENT_DIR="$PROJECT_DIR/agent"
mkdir -p "$AGENT_DIR"
cd "$AGENT_DIR"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cat <<EOF > "$AGENT_DIR/config.env"
TELEGRAM_BOT_TOKEN=$TG_BOT_TOKEN
ADMIN_CHAT_ID=$TG_CHAT_ID
GEMINI_API_KEY=$GEMINI_KEY

CPU_THRESHOLD=85
RAM_THRESHOLD=85
DISK_THRESHOLD=90
CHECK_INTERVAL=180
MONITORED_CONTAINERS=personal-cloud-app,shadowbox,pos-server
AUTO_RESTART=True
SSH_MAX_FAILED_ATTEMPTS=4
DDOS_CONN_THRESHOLD=800
EOF

# Create and Start Systemd Service for Agent
cat <<EOF > /etc/systemd/system/stech-agent.service
[Unit]
Description=S-Tech VPS Server Maintenance & Cyber Defense AI Assistant
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$AGENT_DIR
ExecStart=$AGENT_DIR/venv/bin/python3 $AGENT_DIR/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable stech-agent.service

if [ -n "$TG_BOT_TOKEN" ]; then
    systemctl restart stech-agent.service
    echo -e "${GREEN}✅ AI DevOps Agent service started successfully!${NC}"
else
    echo -e "${YELLOW}⚠️ Agent installed. Please add your Telegram Bot Token in $AGENT_DIR/config.env to start.${NC}"
fi

# Step 5: Optional Nginx & SSL
if [ -n "$DOMAIN_NAME" ]; then
    echo -e "${BLUE}🔒 [6/6] Configuring Nginx Reverse Proxy & Free SSL...${NC}"
    apt install -y nginx certbot python3-certbot-nginx
    
    cat <<EOF > "/etc/nginx/sites-available/$DOMAIN_NAME"
server {
    server_name $DOMAIN_NAME;
    client_max_body_size 10G;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    ln -sf "/etc/nginx/sites-available/$DOMAIN_NAME" "/etc/nginx/sites-enabled/"
    nginx -t && systemctl reload nginx
    certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos --register-unsafely-without-email || true
fi

PUBLIC_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "======================================================================"
echo -e "${GREEN}🎉 ALL-IN-ONE INSTALLATION COMPLETE! S-TECH IS LIVE!${NC}"
echo "======================================================================"
if [ -n "$DOMAIN_NAME" ]; then
    echo -e "🌐 ${CYAN}Cloud URL:${NC}           https://$DOMAIN_NAME"
else
    echo -e "🌐 ${CYAN}Cloud URL:${NC}           http://$PUBLIC_IP:3000"
fi
echo -e "🔑 ${CYAN}Master Password:${NC}     $ADMIN_PASSWORD"
echo -e "🛡️ ${CYAN}Cyber Shield:${NC}        UFW Firewall & SSH Auto-Ban ACTIVE"
echo -e "🤖 ${CYAN}AI DevOps Agent:${NC}     $(systemctl is-active stech-agent.service)"
echo "----------------------------------------------------------------------"
echo -e "📱 ${YELLOW}Tips:${NC} Open the Cloud URL on your Phone/Tablet and click"
echo -e "       ${GREEN}'Add to Home Screen'${NC} to install as a native app!"
echo "======================================================================"

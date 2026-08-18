#!/usr/bin/env python3
"""
S-Tech VPS Server Maintenance & Cyber Defense AI Assistant (v4.2 - Dynamic Model Resolution)
Author: Antigravity
"""

import os
import sys
import time
import asyncio
import subprocess
import logging
import re
import json
import requests
from datetime import datetime
import psutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ContextTypes, filters
)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'config.env'))

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

CPU_THRESHOLD = float(os.getenv('CPU_THRESHOLD', '85'))
RAM_THRESHOLD = float(os.getenv('RAM_THRESHOLD', '85'))
DISK_THRESHOLD = float(os.getenv('DISK_THRESHOLD', '90'))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '180'))
MONITORED_CONTAINERS = [c.strip() for c in os.getenv('MONITORED_CONTAINERS', 'personal-cloud-app').split(',') if c.strip()]
AUTO_RESTART = os.getenv('AUTO_RESTART', 'True').lower() in ('true', '1', 'yes')

SSH_MAX_FAILED_ATTEMPTS = int(os.getenv('SSH_MAX_FAILED_ATTEMPTS', '4'))
DDOS_CONN_THRESHOLD = int(os.getenv('DDOS_CONN_THRESHOLD', '800'))

# Base Storage Directory for Telegram Uploads
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STORAGE_DIR = os.path.join(PROJECT_ROOT, 'storage', 'Telegram_Uploads')
os.makedirs(STORAGE_DIR, exist_ok=True)

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('STechUltraAgent')

# Internal State Tracking
alert_state = {
    'cpu_alerted': False,
    'ram_alerted': False,
    'disk_alerted': False,
    'ddos_alerted': False,
    'containers_down': set(),
    'daily_report_sent_date': None,
    'blocked_ips_today': set(),
    'failed_ssh_attempts': {}
}

# --- System Utilities ---
def format_bytes(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"

def get_uptime():
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m"

def run_cmd(cmd, timeout=35):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip() or res.stderr.strip()
    except Exception as e:
        return f"Error: {str(e)}"

def get_docker_containers():
    out = run_cmd("docker ps -a --format '{{.Names}}|{{.Status}}|{{.State}}'")
    if not out or out.startswith("Error") or "command not found" in out:
        return []
    containers = []
    for line in out.splitlines():
        parts = line.split('|')
        if len(parts) >= 3:
            containers.append({
                'name': parts[0],
                'status': parts[1],
                'state': parts[2]
            })
    return containers

def get_active_connection_count():
    try:
        out = run_cmd("ss -ant | grep -c ESTAB || netstat -an | grep -c ESTABLISHED")
        return int(out) if out.isdigit() else 0
    except:
        return len(psutil.net_connections(kind='inet'))

# --- Security Decorator ---
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.message:
            return
        user_id = str(update.effective_user.id)
        if str(ADMIN_CHAT_ID) and user_id != str(ADMIN_CHAT_ID):
            logger.warning(f"Unauthorized attempt from user_id: {user_id}")
            await update.message.reply_text("⛔ <b>Access Denied!</b> You are not authorized to control this server.", parse_mode="HTML")
            return
        return await func(update, context)
    return wrapper

# --- AI Tools for Gemini Brain ---
def tool_get_system_metrics():
    """Returns real-time CPU, RAM, Swap, Disk, Uptime, IP and network load."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    swap = psutil.swap_memory()
    uptime = get_uptime()
    conns = get_active_connection_count()
    ip = run_cmd("curl -s -m 4 ifconfig.me || hostname -I | awk '{print $1}'")
    return {
        "ip_address": ip,
        "uptime": uptime,
        "cpu_percent": cpu_percent,
        "ram_used": format_bytes(ram.used),
        "ram_total": format_bytes(ram.total),
        "ram_percent": ram.percent,
        "swap_percent": swap.percent,
        "disk_used": format_bytes(disk.used),
        "disk_free": format_bytes(disk.free),
        "disk_percent": disk.percent,
        "active_connections": conns
    }

def tool_manage_docker(action: str, container_name: str = ""):
    """Manages docker containers. Actions: 'list', 'restart', 'logs'."""
    if action == "list":
        return get_docker_containers()
    elif action == "restart" and container_name:
        res = run_cmd(f"docker restart {container_name}")
        return {"action": "restart", "container": container_name, "output": res}
    elif action == "logs" and container_name:
        res = run_cmd(f"docker logs --tail 30 {container_name}")
        return {"action": "logs", "container": container_name, "logs": res}
    return {"error": "Invalid action or container_name"}

def tool_clean_cache():
    """Cleans unused docker images, containers, and temporary system journal logs."""
    prune = run_cmd("docker system prune -f")
    apt = run_cmd("sudo apt clean && sudo journalctl --vacuum-time=3d")
    disk = psutil.disk_usage('/')
    return {"status": "success", "disk_after": f"{disk.percent}% used ({format_bytes(disk.free)} free)", "prune_result": prune}

def tool_backup_data():
    """Creates a full archive backup of S-Tech Cloud and database files."""
    backup_dir = "/root/backups"
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"{backup_dir}/backup_{ts}.tar.gz"
    res = run_cmd(f"tar -czf {file_path} {PROJECT_ROOT}/data {PROJECT_ROOT}/storage 2>/dev/null || tar -czf {file_path} /root/stechcloud 2>/dev/null")
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        return {"status": "success", "file": file_path, "size": format_bytes(size), "bytes": size}
    return {"status": "failed", "error": res}

def tool_manage_firewall(action: str, ip: str = ""):
    """Manages UFW firewall. Actions: 'status', 'ban', 'unban'."""
    if action == "status":
        out = run_cmd("sudo ufw status numbered | head -n 20")
        return {"firewall_rules": out, "blocked_today": list(alert_state['blocked_ips_today'])}
    elif action == "ban" and ip:
        res = run_cmd(f"sudo ufw insert 1 deny from {ip} to any")
        alert_state['blocked_ips_today'].add(ip)
        return {"status": "banned", "ip": ip, "result": res}
    elif action == "unban" and ip:
        res = run_cmd(f"sudo ufw delete deny from {ip}")
        alert_state['blocked_ips_today'].discard(ip)
        return {"status": "unbanned", "ip": ip, "result": res}
    return {"error": "Invalid action"}

def tool_run_speedtest():
    """Runs a network latency and speed test on the VPS."""
    res = run_cmd("curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --simple 2>/dev/null", timeout=40)
    return {"speedtest_output": res or "Speedtest completed"}

def tool_deploy_app(app_type: str, app_name: str = "my-app"):
    """Deploys common docker apps like 'wordpress', 'nginx', 'redis'."""
    app_type = app_type.lower().strip()
    if app_type == "wordpress":
        cmd = f"docker run -d --name {app_name} -p 8080:80 -e WORDPRESS_DB_PASSWORD=secret wordpress:latest"
        res = run_cmd(cmd)
        return {"status": "deployed", "app": "WordPress", "port": 8080, "output": res}
    elif app_type == "nginx":
        cmd = f"docker run -d --name {app_name} -p 8081:80 nginx:alpine"
        res = run_cmd(cmd)
        return {"status": "deployed", "app": "Nginx", "port": 8081, "output": res}
    return {"error": f"Unsupported app_type: {app_type}. Supported: wordpress, nginx"}

def tool_change_password(target: str, new_password: str):
    """Changes password for 'cloud' (S-Tech Cloud) or 'vps' (Linux root)."""
    target = target.lower().strip()
    if not new_password or len(new_password) < 4:
        return {"status": "error", "message": "Password must be at least 4 characters."}
    
    if target in ["cloud", "stechcloud", "storage"]:
        env_path = os.path.join(PROJECT_ROOT, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                content = f.read()
            if 'ADMIN_PASSWORD=' in content:
                content = re.sub(r'ADMIN_PASSWORD=.*', f'ADMIN_PASSWORD={new_password}', content)
            else:
                content += f"\nADMIN_PASSWORD={new_password}\n"
            with open(env_path, 'w') as f:
                f.write(content)
            
            # Restart container to apply new password
            run_cmd("docker restart personal-cloud-app")
            return {"status": "success", "target": "S-Tech Cloud", "message": "Cloud Master Password updated and container reloaded successfully!"}
        return {"status": "error", "message": ".env file not found."}
    
    elif target in ["vps", "root", "server", "linux"]:
        res = run_cmd(f'echo "root:{new_password}" | sudo chpasswd')
        return {"status": "success", "target": "VPS Linux Root", "message": "VPS Root Password changed successfully!"}
    
    return {"status": "error", "message": "Invalid target. Choose 'cloud' or 'vps'."}

def tool_run_safe_command(command: str):
    """Runs safe Linux diagnostic commands."""
    forbidden = ["rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "chmod -R 777 /", "> /dev/sda", "shutdown"]
    for f in forbidden:
        if f in command.lower():
            return {"error": f"Security Block: Command '{command}' is prohibited."}
    out = run_cmd(command, timeout=25)
    return {"command": command, "output": out}

# Dynamic Gemini AI Auto-Discovery & Initialization
active_model_name = None
if GEMINI_AVAILABLE and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Discover all available models in the API key
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in getattr(m, 'supported_generation_methods', [])]
            logger.info(f"Discovered Gemini models: {available_models}")
            
            # Prefer flash or pro models
            for target in ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash', 'gemini-pro']:
                for m in available_models:
                    if target in m:
                        active_model_name = m.replace('models/', '')
                        break
                if active_model_name:
                    break
        except Exception as le:
            logger.warning(f"Could not list models dynamically: {le}")

        if not active_model_name:
            active_model_name = "gemini-1.5-flash"

        logger.info(f"Using Gemini model: {active_model_name}")

    except Exception as e:
        logger.error(f"Failed to initialize Gemini AI: {e}")

# Direct REST & SDK AI query helper
def ask_gemini(user_text: str) -> str:
    """Queries Gemini AI with full system context and real-time server metrics."""
    metrics = tool_get_system_metrics()
    containers = get_docker_containers()
    blocked_count = len(alert_state['blocked_ips_today'])

    context_prompt = (
        "You are S-Tech AI DevOps Engineer & Assistant - an intelligent server administrator for the owner's DigitalOcean VPS.\n"
        "Here is the LIVE real-time server state:\n"
        f"- IP Address: {metrics['ip_address']}\n"
        f"- Uptime: {metrics['uptime']}\n"
        f"- CPU Usage: {metrics['cpu_percent']}%\n"
        f"- RAM: {metrics['ram_percent']}% used ({metrics['ram_used']} / {metrics['ram_total']})\n"
        f"- Disk Storage: {metrics['disk_percent']}% used ({metrics['disk_used']} / {metrics['disk_free']} free)\n"
        f"- Active Connections: {metrics['active_connections']}\n"
        f"- Docker Containers: {json.dumps(containers)}\n"
        f"- Blocked Hacker IPs Today: {blocked_count}\n\n"
        "Rules:\n"
        "1. Respond in natural, polite, and fluent Burmese (မြန်မာဘာသာ) with helpful formatting and emojis.\n"
        "2. Directly answer the user's question using the live data above.\n"
        "3. If the user asks you to clean cache, restart containers, or backup, explain that you can perform it and recommend the action.\n\n"
        f"User Question: {user_text}"
    )

    # Strategy 1: Use direct Google REST API (fastest & 100% reliable)
    for model_candidate in [active_model_name, "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]:
        if not model_candidate:
            continue
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_candidate}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": context_prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
            }
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                text = data['candidates'][0]['content']['parts'][0]['text']
                return text.strip()
            else:
                logger.warning(f"REST API error with {model_candidate}: {resp.status_code} {resp.text}")
        except Exception as ex:
            logger.warning(f"Error calling {model_candidate}: {ex}")

    # Strategy 2: Python SDK fallback
    try:
        model = genai.GenerativeModel(active_model_name or "gemini-1.5-flash")
        response = model.generate_content(context_prompt)
        return response.text.strip()
    except Exception as e:
        raise e

# --- Direct Telegram File Upload to Cloud Handler ---
@admin_only
async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file_obj = None
    original_name = ""

    if msg.photo:
        file_obj = await msg.photo[-1].get_file()
        original_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    elif msg.video:
        file_obj = await msg.video.get_file()
        original_name = msg.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    elif msg.audio:
        file_obj = await msg.audio.get_file()
        original_name = msg.audio.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
    elif msg.document:
        file_obj = await msg.document.get_file()
        original_name = msg.document.file_name or f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"

    if file_obj and original_name:
        status_msg = await msg.reply_text(f"⏳ <b>Uploading to S-Tech Cloud:</b> <code>{original_name}</code>...", parse_mode="HTML")
        dest_path = os.path.join(STORAGE_DIR, original_name)
        
        await file_obj.download_to_drive(dest_path)
        file_size = os.path.getsize(dest_path)

        await status_msg.edit_text(
            f"✅ <b>Saved to S-Tech Cloud!</b>\n\n"
            f"📁 <b>Folder:</b> <code>Telegram_Uploads/{original_name}</code>\n"
            f"📦 <b>Size:</b> {format_bytes(file_size)}\n\n"
            f"🌐 <i>You can now access, stream, or download this file from your S-Tech Cloud app!</i>",
            parse_mode="HTML"
        )

# --- Natural Language Message Handler (AI Brain Chat) ---
@admin_only
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if not user_text:
        return

    # Check for direct action intents
    lowered = user_text.lower()
    if "အမှိုက်" in user_text or "clean" in lowered or "ရှင်း" in user_text:
        await cmd_clean(update, context)
        return
    elif "backup" in lowered or "ဘက်ကပ်" in user_text:
        await cmd_backup(update, context)
        return
    elif "speed" in lowered or "လိုင်းမြန်" in user_text:
        await cmd_speedtest(update, context)
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text(
            "ℹ️ <b>AI Brain is in Standard Command Mode.</b>\n"
            "Add your free <code>GEMINI_API_KEY</code> in <code>config.env</code> to chat in natural Burmese.\n"
            "Try: /status, /containers, /clean, /backup, /security.",
            parse_mode="HTML"
        )
        return

    await update.message.chat.send_action("typing")

    try:
        reply_text = await asyncio.to_thread(ask_gemini, user_text)
        await update.message.reply_text(reply_text or "အဆင်ပြေစွာ ဆောင်ရွက်ပြီးစီးပါပြီခင်ဗျာ။")
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        # Graceful fallback: return system status report
        m = tool_get_system_metrics()
        fallback_msg = (
            f"🖥️ <b>S-Tech Server အခြေအနေ အကျဉ်းချုပ်:</b>\n\n"
            f"⚙️ <b>CPU:</b> {m['cpu_percent']}%\n"
            f"🧠 <b>RAM:</b> {m['ram_percent']}% ({m['ram_used']} / {m['ram_total']})\n"
            f"💾 <b>Storage:</b> {m['disk_percent']}% ({m['disk_used']} used / {m['disk_free']} free)\n"
            f"⏱️ <b>Uptime:</b> {m['uptime']}\n\n"
            f"အသေးစိတ်ကြည့်ရန် /status သို့မဟုတ် /security ကို အသုံးပြုနိုင်ပါသည်ခင်ဗျာ။"
        )
        await update.message.reply_text(fallback_msg, parse_mode="HTML")

# --- Bot Command Handlers ---

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 <b>Welcome to S-Tech AI DevOps & Cyber Defense Assistant (v4.2)</b>\n\n"
        "💬 <b>Natural AI Chat:</b> Chat with me in Burmese anytime! (e.g. <i>'ဆာဗာ အခြေအနေ ဘယ်လိုလဲ'</i>, <i>'RAM ရှင်းပေး'</i>)\n\n"
        "📤 <b>Cloud File Upload:</b> Send any photo/video/doc here to save directly into S-Tech Cloud!\n\n"
        "<b>Direct Commands:</b>\n"
        "📊 /status - System metrics (CPU, RAM, Disk, Uptime)\n"
        "📦 /containers - Docker containers status\n"
        "🔄 /restart &lt;name&gt; - Restart a Docker container\n"
        "📜 /logs &lt;name&gt; - View container logs\n"
        "🧹 /clean - Clean unused cache & docker logs\n"
        "💾 /backup - Backup Cloud & deliver file to Telegram\n"
        "🛡️ /security - Security audit & blocked attackers\n"
        "🚀 /speedtest - Test VPS network speed\n"
        "📋 /report - Instant Full Health Report\n"
        "⚠️ /reboot - Reboot the VPS server"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = tool_get_system_metrics()
    containers = get_docker_containers()
    running_c = sum(1 for c in containers if c['state'] == 'running')
    total_c = len(containers)

    msg = (
        f"🖥️ <b>S-Tech Server Health & Security Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>IP:</b> <code>{m['ip_address']}</code>\n"
        f"⏱️ <b>Uptime:</b> {m['uptime']}\n"
        f"🔗 <b>Active Network Connections:</b> {m['active_connections']}\n\n"
        f"⚙️ <b>CPU Load:</b> {m['cpu_percent']}%\n"
        f"🧠 <b>RAM Usage:</b> {m['ram_percent']}% ({m['ram_used']} / {m['ram_total']})\n"
        f"💽 <b>Swap:</b> {m['swap_percent']}%\n"
        f"💾 <b>Disk Storage:</b> {m['disk_percent']}% ({m['disk_used']} used / {m['disk_free']} free)\n\n"
        f"📦 <b>Containers:</b> {running_c}/{total_c} Running\n"
        f"🛡️ <b>Blocked Attacks Today:</b> {len(alert_state['blocked_ips_today'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <i>Status: Optimal & Protected</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("💾 Creating backup archive of S-Tech Cloud data...")
    res = tool_backup_data()
    
    if res.get('status') == 'success':
        file_path = res['file']
        file_size = res.get('bytes', 0)
        
        await status_msg.edit_text(f"✅ Backup created ({res['size']})! Sending to Telegram...")
        
        if file_size < 48 * 1024 * 1024 and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(file_path),
                    caption=f"📦 <b>S-Tech Cloud Backup Archive</b>\nSize: {res['size']}",
                    parse_mode="HTML"
                )
        else:
            await update.message.reply_text(f"📁 Backup saved locally at <code>{file_path}</code> (Size: {res['size']}).", parse_mode="HTML")
    else:
        await status_msg.edit_text(f"❌ Backup failed: {res.get('error')}")

@admin_only
async def cmd_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fw = tool_manage_firewall("status")
    blocked_list = "\n".join([f"• <code>{ip}</code>" for ip in fw.get('blocked_today', [])[-10:]]) or "None today"

    msg = (
        f"🛡️ <b>Cyber Security & Intrusion Shield Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <b>Firewall:</b> Active (UFW & Fail2ban)\n"
        f"🚫 <b>Attacks Blocked Today:</b> {len(alert_state['blocked_ips_today'])}\n\n"
        f"<b>Recently Blocked Attacker IPs:</b>\n{blocked_list}\n\n"
        f"<b>Firewall Rule Preview:</b>\n<pre>{fw.get('firewall_rules', 'N/A')}</pre>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/ban &lt;IP_ADDRESS&gt;</code>", parse_mode="HTML")
        return
    ip = context.args[0].strip()
    res = tool_manage_firewall("ban", ip)
    await update.message.reply_text(f"🚫 <b>IP Banned!</b> <code>{ip}</code> has been blocked in firewall.", parse_mode="HTML")

@admin_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/unban &lt;IP_ADDRESS&gt;</code>", parse_mode="HTML")
        return
    ip = context.args[0].strip()
    res = tool_manage_firewall("unban", ip)
    await update.message.reply_text(f"🔓 <b>IP Unbanned:</b> <code>{ip}</code> removed from blocklist.", parse_mode="HTML")

@admin_only
async def cmd_containers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    containers = get_docker_containers()
    if not containers:
        await update.message.reply_text("ℹ️ No Docker containers found.")
        return

    msg = "📦 <b>Docker Containers List:</b>\n\n"
    for c in containers:
        icon = "🟢" if c['state'] == 'running' else "🔴"
        msg += f"{icon} <b>{c['name']}</b>\n   └ Status: {c['status']}\n\n"

    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/restart &lt;container_name&gt;</code>", parse_mode="HTML")
        return
    c_name = context.args[0]
    await update.message.reply_text(f"⏳ Restarting container <code>{c_name}</code>...", parse_mode="HTML")
    res = tool_manage_docker("restart", c_name)
    await update.message.reply_text(f"✅ Restart result for <code>{c_name}</code>:\n{res.get('output')}", parse_mode="HTML")

@admin_only
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/logs &lt;container_name&gt;</code>", parse_mode="HTML")
        return
    c_name = context.args[0]
    res = tool_manage_docker("logs", c_name)
    logs = res.get('logs', '')[-3500:]
    await update.message.reply_text(f"📜 <b>Recent Logs for {c_name}:</b>\n<pre>{logs or 'No logs.'}</pre>", parse_mode="HTML")

@admin_only
async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧹 Cleaning up unused Docker images and cache...")
    res = tool_clean_cache()
    await update.message.reply_text(f"✅ <b>Cleanup Complete!</b>\n💽 Current Disk: {res.get('disk_after')}", parse_mode="HTML")

@admin_only
async def cmd_speedtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Running VPS network latency & speed test (takes ~15s)...")
    res = tool_run_speedtest()
    await update.message.reply_text(f"📡 <b>Speedtest Results:</b>\n<pre>{res.get('speedtest_output')}</pre>", parse_mode="HTML")

@admin_only
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_report(context.application)

@admin_only
async def cmd_passwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "🔑 <b>Password Change Usage:</b>\n\n"
            "• <b>Cloud Password ပြောင်းရန်:</b>\n<code>/passwd cloud &lt;new_password&gt;</code>\n\n"
            "• <b>VPS Linux Root Password ပြောင်းရန်:</b>\n<code>/passwd vps &lt;new_password&gt;</code>",
            parse_mode="HTML"
        )
        return
    
    target = context.args[0]
    new_pwd = context.args[1]
    
    status_msg = await update.message.reply_text(f"⏳ Updating <b>{target}</b> password...", parse_mode="HTML")
    res = tool_change_password(target, new_pwd)
    
    if res.get('status') == 'success':
        await status_msg.edit_text(
            f"✅ <b>Password Changed Successfully!</b>\n\n"
            f"🎯 <b>Target:</b> {res.get('target')}\n"
            f"🔐 <b>New Password:</b> <code>{new_pwd}</code>\n\n"
            f"<i>Your new credentials are now active!</i>",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(f"❌ <b>Error:</b> {res.get('message')}", parse_mode="HTML")

@admin_only
async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text("⚠️ <b>Warning:</b> This will reboot the entire VPS.\nTo proceed, type: <code>/reboot confirm</code>", parse_mode="HTML")
        return
    await update.message.reply_text("🔄 Rebooting server now... The bot will reconnect in ~1-2 minutes.")
    subprocess.Popen(["sudo", "reboot"])

# --- Security Scanner & Background Monitor ---
async def scan_ssh_brute_force(app: Application):
    try:
        log_out = run_cmd("sudo journalctl -u ssh --since '10 minutes ago' | grep -i 'Failed password'")
        if not log_out:
            return

        ip_pattern = r'from (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        matches = re.findall(ip_pattern, log_out)

        for ip in matches:
            if ip.startswith(('127.', '10.', '192.168.', '172.16.')):
                continue

            alert_state['failed_ssh_attempts'][ip] = alert_state['failed_ssh_attempts'].get(ip, 0) + 1

            if alert_state['failed_ssh_attempts'][ip] >= SSH_MAX_FAILED_ATTEMPTS:
                if ip not in alert_state['blocked_ips_today']:
                    run_cmd(f"sudo ufw insert 1 deny from {ip} to any")
                    alert_state['blocked_ips_today'].add(ip)

                    msg = (
                        f"🛡️ <b>CYBER INTRUSION BLOCKED!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚨 <b>Attacker IP:</b> <code>{ip}</code>\n"
                        f"⚠️ <b>Reason:</b> Repeated SSH Password Brute-Force ({alert_state['failed_ssh_attempts'][ip]} failed attempts)\n"
                        f"🔒 <b>Action Taken:</b> IP permanently BANNED in Firewall (UFW)\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in SSH scan: {e}")

async def send_daily_report(app: Application):
    try:
        if not ADMIN_CHAT_ID:
            return

        m = tool_get_system_metrics()
        containers = get_docker_containers()
        running_c = sum(1 for c in containers if c['state'] == 'running')
        total_c = len(containers)
        blocked_count = len(alert_state['blocked_ips_today'])
        today_str = datetime.now().strftime("%d-%b-%Y")

        report_msg = (
            f"📋 <b>S-Tech Server Daily Report ({today_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Status:</b> 100% Operational & Healthy\n"
            f"⏱️ <b>Uptime:</b> {m['uptime']}\n"
            f"🧠 <b>RAM Usage:</b> {m['ram_percent']}% ({m['ram_used']} / {m['ram_total']})\n"
            f"💾 <b>Disk Usage:</b> {m['disk_percent']}% ({m['disk_free']} free space)\n"
            f"📦 <b>Services:</b> {running_c}/{total_c} Containers Online\n"
            f"🛡️ <b>Security:</b> {blocked_count} Attacks Blocked Today\n"
            f"🌐 <b>Active Connections:</b> {m['active_connections']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Everything is running smoothly! Have a wonderful day!</i>"
        )
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=report_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending daily report: {e}")

async def monitor_loop(app: Application):
    logger.info("Background health & security monitor started.")
    await asyncio.sleep(10)

    while True:
        try:
            if not ADMIN_CHAT_ID:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            now = datetime.now()

            # 1. Daily Report at 08:00 AM
            today_date = now.date()
            if now.hour == 8 and alert_state['daily_report_sent_date'] != today_date:
                await send_daily_report(app)
                alert_state['daily_report_sent_date'] = today_date
                alert_state['blocked_ips_today'].clear()
                alert_state['failed_ssh_attempts'].clear()

            # 2. Cyber Intrusion Check
            await scan_ssh_brute_force(app)

            # 3. DDoS Connection Spike Check
            active_conns = get_active_connection_count()
            if active_conns >= DDOS_CONN_THRESHOLD:
                if not alert_state['ddos_alerted']:
                    msg = f"🚨 <b>POTENTIAL DDoS DETECTED!</b> Active connections reached <b>{active_conns}</b>."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['ddos_alerted'] = True
            else:
                alert_state['ddos_alerted'] = False

            # 4. Check RAM
            ram = psutil.virtual_memory()
            if ram.percent >= RAM_THRESHOLD:
                if not alert_state['ram_alerted']:
                    msg = f"🚨 <b>HIGH RAM ALERT!</b> RAM usage reached <b>{ram.percent}%</b> ({format_bytes(ram.used)}/{format_bytes(ram.total)})."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['ram_alerted'] = True
            else:
                alert_state['ram_alerted'] = False

            # 5. Check Disk
            disk = psutil.disk_usage('/')
            if disk.percent >= DISK_THRESHOLD:
                if not alert_state['disk_alerted']:
                    msg = f"🚨 <b>HIGH DISK ALERT!</b> Disk usage is at <b>{disk.percent}%</b>. Run /clean to free up space."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['disk_alerted'] = True
            else:
                alert_state['disk_alerted'] = False

            # 6. Check actually running Monitored Containers & Auto-Restart
            containers = get_docker_containers()
            existing_container_names = [c['name'] for c in containers]
            container_dict = {c['name']: c for c in containers}

            for target_name in MONITORED_CONTAINERS:
                if target_name not in existing_container_names:
                    continue

                c = container_dict.get(target_name)
                if not c or c['state'] != 'running':
                    if target_name not in alert_state['containers_down']:
                        alert_state['containers_down'].add(target_name)
                        alert_msg = f"⚠️ <b>CONTAINER DOWN!</b> Service <code>{target_name}</code> has stopped!"
                        
                        if AUTO_RESTART and c:
                            alert_msg += "\n🔄 <i>Attempting auto-restart...</i>"
                            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_msg, parse_mode="HTML")
                            run_cmd(f"docker restart {target_name}")
                            await asyncio.sleep(5)
                            
                            updated = get_docker_containers()
                            is_running = any(uc['name'] == target_name and uc['state'] == 'running' for uc in updated)
                            if is_running:
                                await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"✅ Auto-restart successful for <code>{target_name}</code>!", parse_mode="HTML")
                                alert_state['containers_down'].discard(target_name)
                        else:
                            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_msg, parse_mode="HTML")
                else:
                    alert_state['containers_down'].discard(target_name)

        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL)

def main():
    if not BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is not set in config.env")
        sys.exit(1)

    print("🚀 Starting S-Tech AI DevOps & Cyber Defense Assistant (v4.2)...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Direct File Upload Handlers (Photo, Video, Audio, Document -> S-Tech Cloud)
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.Document.ALL, handle_file_upload))

    # Command Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("security", cmd_security))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("containers", cmd_containers))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("clean", cmd_clean))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("speedtest", cmd_speedtest))
    app.add_handler(CommandHandler("passwd", cmd_passwd))
    app.add_handler(CommandHandler("password", cmd_passwd))
    app.add_handler(CommandHandler("reboot", cmd_reboot))

    # Natural Language AI Brain Chat Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))

    async def post_init(application: Application):
        asyncio.create_task(monitor_loop(application))
        if ADMIN_CHAT_ID:
            try:
                brain_status = f"🧠 Gemini AI Brain: ACTIVATED ({active_model_name})" if active_model_name else "⚙️ Command Mode Active"
                await application.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"🤖 <b>S-Tech AI DevOps Assistant (v4.2) is ONLINE!</b>\n{brain_status}\n\n• Type /status to inspect VPS\n• Send any file/photo to save to Cloud\n• Send any message to chat in Burmese.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")

    app.post_init = post_init
    app.run_polling()

if __name__ == '__main__':
    main()

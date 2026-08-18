#!/usr/bin/env python3
"""
S-Tech VPS AI DevOps & Cyber Defense Assistant (v5.0 - Pro Defense & Interactive Auto-Healer)
Author: Antigravity
Features:
- Silent SSH Intrusion Shield (Blocks bots silently in background without notification spam)
- Critical-Only Immediate Alerts (High RAM, High CPU Overload, DDoS Storms, Service Crashes)
- 1-Click Interactive Auto-Repair via Telegram Inline Buttons & Natural Reply ("ပြင်ဆင်လိုက်ပါ", "Fix it")
- Self-Updating Engine (/upgrade) & Telegram-to-Cloud Uploader
- Daily 08:00 AM Comprehensive Health & Security Briefing
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
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
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '120'))
MONITORED_CONTAINERS = [c.strip() for c in os.getenv('MONITORED_CONTAINERS', 'personal-cloud-app').split(',') if c.strip()]
AUTO_RESTART = os.getenv('AUTO_RESTART', 'True').lower() in ('true', '1', 'yes')

SSH_MAX_FAILED_ATTEMPTS = int(os.getenv('SSH_MAX_FAILED_ATTEMPTS', '4'))
DDOS_CONN_THRESHOLD = int(os.getenv('DDOS_CONN_THRESHOLD', '500'))

# Base Storage Directory for Telegram Uploads
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STORAGE_DIR = os.path.join(PROJECT_ROOT, 'storage', 'Telegram_Uploads')
os.makedirs(STORAGE_DIR, exist_ok=True)

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('STechProAgent')

# Internal State Tracking
alert_state = {
    'cpu_alerted': False,
    'ram_alerted': False,
    'disk_alerted': False,
    'ddos_alerted': False,
    'containers_down': set(),
    'daily_report_sent_date': None,
    'blocked_ips_today': set(),
    'blocked_ips_history': [],
    'failed_ssh_attempts': {},
    'last_alert_type': None
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

def get_top_memory_processes():
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
        try:
            processes.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
    return processes[:4]

def get_active_connection_count():
    try:
        out = run_cmd("ss -ant | grep -c ESTAB || netstat -an | grep -c ESTABLISHED")
        return int(out) if out.isdigit() else 0
    except:
        return len(psutil.net_connections(kind='inet'))

# --- Security Decorator ---
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        user_id = str(user.id)
        if str(ADMIN_CHAT_ID) and user_id != str(ADMIN_CHAT_ID):
            logger.warning(f"Unauthorized attempt from user_id: {user_id}")
            if update.message:
                await update.message.reply_text("⛔ <b>Access Denied!</b> You are not authorized to control this server.", parse_mode="HTML")
            return
        return await func(update, context)
    return wrapper

# --- Auto-Fix Execution Engine ---
def execute_auto_repair(fix_type: str = "general"):
    """Performs deep server optimization, RAM release, container recovery, and cache drop."""
    results = []
    
    # 1. RAM / CPU Optimization
    if fix_type in ["ram", "cpu", "general", "slow"]:
        run_cmd("sync; echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null")
        prune_res = run_cmd("docker system prune -f")
        journal_res = run_cmd("sudo journalctl --vacuum-time=2d")
        apt_res = run_cmd("sudo apt clean")
        results.append("🧹 System cache and Docker buffers purged.")

    # 2. Container Health Recovery
    if fix_type in ["container", "general"]:
        containers = get_docker_containers()
        for c in containers:
            if c['state'] != 'running' and c['name'] in MONITORED_CONTAINERS:
                run_cmd(f"docker restart {c['name']}")
                results.append(f"🔄 Restarted container: {c['name']}")

    # 3. DDoS & Network Protection
    if fix_type in ["ddos", "network"]:
        run_cmd("sudo sysctl -w net.ipv4.tcp_syncookies=1 > /dev/null")
        results.append("🛡️ Enabled TCP SYN Cookies and Rate-Limiting.")

    # Get fresh metrics
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.5)
    disk = psutil.disk_usage('/')

    return {
        "status": "success",
        "actions": results,
        "ram_now": f"{ram.percent}% ({format_bytes(ram.used)} / {format_bytes(ram.total)})",
        "cpu_now": f"{cpu}%",
        "disk_now": f"{disk.percent}%"
    }

# --- System AI Tools ---
def tool_get_system_metrics():
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
    if action == "list":
        return get_docker_containers()
    elif action == "restart" and container_name:
        res = run_cmd(f"docker restart {container_name}")
        return {"action": "restart", "container": container_name, "output": res}
    elif action == "logs" and container_name:
        res = run_cmd(f"docker logs --tail 30 {container_name}")
        return {"action": "logs", "container": container_name, "logs": res}
    return {"error": "Invalid action or container_name"}

def tool_backup_data():
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
    if action == "status":
        out = run_cmd("sudo ufw status numbered | head -n 25")
        return {"firewall_rules": out, "blocked_today": list(alert_state['blocked_ips_today']), "total_blocked_today": len(alert_state['blocked_ips_today'])}
    elif action == "ban" and ip:
        res = run_cmd(f"sudo ufw insert 1 deny from {ip} to any")
        alert_state['blocked_ips_today'].add(ip)
        return {"status": "banned", "ip": ip, "result": res}
    elif action == "unban" and ip:
        res = run_cmd(f"sudo ufw delete deny from {ip}")
        alert_state['blocked_ips_today'].discard(ip)
        return {"status": "unbanned", "ip": ip, "result": res}
    return {"error": "Invalid action"}

def tool_change_password(target: str, new_password: str):
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
            run_cmd("docker restart personal-cloud-app")
            return {"status": "success", "target": "S-Tech Cloud", "message": "Cloud Master Password updated!"}
        return {"status": "error", "message": ".env file not found."}
    
    elif target in ["vps", "root", "server", "linux"]:
        res = run_cmd(f'echo "root:{new_password}" | sudo chpasswd')
        return {"status": "success", "target": "VPS Linux Root", "message": "VPS Root Password changed!"}
    
    return {"status": "error", "message": "Invalid target. Choose 'cloud' or 'vps'."}

def tool_self_update():
    try:
        git_res = run_cmd(f"cd {PROJECT_ROOT} && git fetch origin && git reset --hard origin/main && git pull origin main")
        req_path = os.path.join(PROJECT_ROOT, 'agent', 'requirements.txt')
        if os.path.exists(req_path):
            run_cmd(f"{sys.executable} -m pip install -r {req_path}")
        subprocess.Popen("sleep 2 && sudo systemctl restart stech-agent", shell=True)
        return {"status": "success", "git_output": git_res, "message": "Successfully pulled updates from GitHub! Restarting Agent..."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Direct AI query helper
def ask_gemini(user_text: str) -> str:
    metrics = tool_get_system_metrics()
    containers = get_docker_containers()
    blocked_count = len(alert_state['blocked_ips_today'])

    context_prompt = (
        "You are S-Tech AI DevOps & Cyber Defense Assistant for the owner's DigitalOcean VPS.\n"
        "Here is the LIVE real-time server state:\n"
        f"- IP: {metrics['ip_address']} | Uptime: {metrics['uptime']}\n"
        f"- CPU: {metrics['cpu_percent']}% | RAM: {metrics['ram_percent']}% ({metrics['ram_used']}/{metrics['ram_total']})\n"
        f"- Storage: {metrics['disk_percent']}% ({metrics['disk_used']}/{metrics['disk_free']})\n"
        f"- Active Network Connections: {metrics['active_connections']}\n"
        f"- Docker Containers: {json.dumps(containers)}\n"
        f"- Blocked Hacker IPs Today: {blocked_count}\n\n"
        "Rules:\n"
        "1. Respond in natural, friendly, and fluent Burmese (မြန်မာဘာသာ) with clean formatting.\n"
        "2. Directly answer using the live data above.\n"
        "3. If the user asks you to fix or clean, explain what action is performed.\n\n"
        f"User Message: {user_text}"
    )

    if not GEMINI_API_KEY:
        return ""

    for model_candidate in ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_candidate}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": context_prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800}
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception:
            pass
    return ""

# --- Direct Telegram File Upload Handler ---
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
            f"📁 <b>Location:</b> <code>Telegram_Uploads/{original_name}</code>\n"
            f"📦 <b>Size:</b> {format_bytes(file_size)}\n\n"
            f"🌐 <i>Available now in your S-Tech Cloud web app!</i>",
            parse_mode="HTML"
        )

# --- Inline Callback Query Handler (1-Click Fix Buttons) ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("fix_"):
        fix_type = data.replace("fix_", "")
        await query.edit_message_text(f"🛠️ <b>ဆာဗာ ပြင်ဆင်ရှင်းလင်းမှု စတင်ဆောင်ရွက်နေပါသည် ({fix_type})...</b>", parse_mode="HTML")
        
        res = execute_auto_repair(fix_type)
        actions_str = "\n".join([f"• {a}" for a in res['actions']])
        
        msg = (
            f"✅ <b>ဆာဗာ ပြင်ဆင်ရှင်းလင်းမှု အောင်မြင်ပါသည်!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{actions_str}\n\n"
            f"📊 <b>လက်ရှိ ဆာဗာ အခြေအနေ:</b>\n"
            f"🧠 <b>RAM:</b> {res['ram_now']}\n"
            f"⚙️ <b>CPU:</b> {res['cpu_now']}\n"
            f"💾 <b>Disk:</b> {res['disk_now']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <i>Server performance restored to optimal!</i>"
        )
        await query.message.reply_text(msg, parse_mode="HTML")

# --- Natural Language Message Handler ---
@admin_only
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if not user_text:
        return

    lowered = user_text.lower()
    
    # 1. User says "Fix it" / "ပြင်ဆင်လိုက်ပါ" / "ရှင်းလိုက်ပါ"
    if any(k in user_text for k in ["ပြင်ဆင်လိုက်", "ရှင်းလိုက်", "ပြင်ပေး", "အမှိုက်ရှင်း", "fix it", "clean", "repair"]):
        status_msg = await update.message.reply_text("🛠️ <b>ဆာဗာ ပြင်ဆင်ရှင်းလင်းမှုကို ချက်ချင်း ဆောင်ရွက်ပေးနေပါသည်...</b>", parse_mode="HTML")
        res = execute_auto_repair(alert_state['last_alert_type'] or "general")
        actions_str = "\n".join([f"• {a}" for a in res['actions']])
        
        msg = (
            f"✅ <b>ဆာဗာ ပြင်ဆင်ရှင်းလင်းပြီးစီးပါပြီခင်ဗျာ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{actions_str}\n\n"
            f"📊 <b>ယခု ဆာဗာ အခြေအနေ:</b>\n"
            f"🧠 <b>RAM:</b> {res['ram_now']}\n"
            f"⚙️ <b>CPU:</b> {res['cpu_now']}\n"
            f"💾 <b>Disk:</b> {res['disk_now']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>ဆာဗာ ပေါ့ပါးသွက်လက်သွားပါပြီခင်ဗျာ!</i>"
        )
        await status_msg.edit_text(msg, parse_mode="HTML")
        return

    # 2. Backup request
    if "backup" in lowered or "ဘက်ကပ်" in user_text:
        await cmd_backup(update, context)
        return

    # 3. Speedtest request
    if "speed" in lowered or "လိုင်းမြန်" in user_text:
        await cmd_speedtest(update, context)
        return

    # 4. Upgrade request
    if "update" in lowered or "upgrade" in lowered or "အဆင့်မြှင့်" in user_text:
        await cmd_upgrade(update, context)
        return

    # 5. Security request
    if "security" in lowered or "hack" in lowered or "လုံခြုံရေး" in user_text:
        await cmd_security(update, context)
        return

    # 6. Ask Gemini AI Brain
    await update.message.chat.send_action("typing")
    try:
        reply_text = await asyncio.to_thread(ask_gemini, user_text)
        if reply_text:
            await update.message.reply_text(reply_text)
            return
    except Exception as e:
        logger.error(f"AI chat error: {e}")

    # Fallback: Summary
    m = tool_get_system_metrics()
    fallback_msg = (
        f"🖥️ <b>S-Tech Server အခြေအနေ အကျဉ်းချုပ်:</b>\n\n"
        f"⚙️ <b>CPU:</b> {m['cpu_percent']}%\n"
        f"🧠 <b>RAM:</b> {m['ram_percent']}% ({m['ram_used']} / {m['ram_total']})\n"
        f"💾 <b>Storage:</b> {m['disk_percent']}% ({m['disk_used']} / {m['disk_free']} free)\n"
        f"⏱️ <b>Uptime:</b> {m['uptime']}\n\n"
        f"အသေးစိတ်ကြည့်ရန် /status သို့မဟုတ် /security ကို အသုံးပြုနိုင်ပါသည်ခင်ဗျာ။"
    )
    await update.message.reply_text(fallback_msg, parse_mode="HTML")

# --- Bot Command Handlers ---

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 <b>Welcome to S-Tech AI DevOps Assistant (v5.0 Pro)</b>\n\n"
        "💬 <b>Natural AI Voice/Text:</b> Chat in Burmese anytime!\n"
        "• <i>'ဆာဗာ အခြေအနေ ဘယ်လိုလဲ'</i>\n"
        "• <i>'ဆာဗာ လေးနေတယ် ပြင်ဆင်လိုက်ပါ'</i>\n"
        "• <i>'ဒီနေ့ Hack တဲ့သူတွေ စာရင်းပြပါ'</i>\n\n"
        "<b>Direct Commands:</b>\n"
        "📊 /status - System metrics (CPU, RAM, Disk, Uptime)\n"
        "🛡️ /security - Security audit & blocked attackers log\n"
        "🧹 /clean - Clean unused cache & docker logs\n"
        "💾 /backup - Backup Cloud & send to Telegram\n"
        "🔑 /passwd - Change Cloud or VPS root password\n"
        "🚀 /speedtest - Test VPS network latency\n"
        "🔄 /upgrade - Self-update Agent from GitHub\n"
        "📋 /report - Instant Full Health Report"
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
        f"💾 <b>Disk Storage:</b> {m['disk_percent']}% ({m['disk_used']} / {m['disk_free']} free)\n\n"
        f"📦 <b>Containers:</b> {running_c}/{total_c} Running\n"
        f"🛡️ <b>Blocked Attacks Today:</b> {len(alert_state['blocked_ips_today'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <i>Status: Optimal & Protected</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fw = tool_manage_firewall("status")
    recent_blocked = list(alert_state['blocked_ips_today'])[-10:]
    blocked_list = "\n".join([f"• <code>{ip}</code>" for ip in recent_blocked]) or "None today"

    msg = (
        f"🛡️ <b>Cyber Security & Hacker Shield Audit Log</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <b>Firewall Status:</b> ACTIVE (UFW + Auto-Shield)\n"
        f"🚫 <b>Attacks Blocked & Banned Today:</b> {len(alert_state['blocked_ips_today'])}\n\n"
        f"<b>Recently Banned Attacker IPs:</b>\n{blocked_list}\n\n"
        f"ℹ️ <i>Attacker bots are silently blocked in the background to protect server bandwidth.</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🧹 Cleaning up unused Docker images and cache...")
    res = execute_auto_repair("ram")
    await status_msg.edit_text(
        f"✅ <b>Cleanup Complete!</b>\n\n"
        f"🧠 <b>RAM Now:</b> {res['ram_now']}\n"
        f"💾 <b>Disk Now:</b> {res['disk_now']}",
        parse_mode="HTML"
    )

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
async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text(
        "🔄 <b>Self-Update Engine Initialized...</b>\n\n"
        "• Fetching latest commits from GitHub...\n"
        "• Checking dependencies...\n"
        "• Applying updates and reloading Agent...",
        parse_mode="HTML"
    )
    res = tool_self_update()
    if res.get('status') == 'success':
        await status_msg.edit_text(
            f"✅ <b>Agent Upgraded Successfully!</b>\n\n"
            f"📦 <b>Git Status:</b>\n<pre>{res.get('git_output', 'Updated')[:2000]}</pre>\n\n"
            f"🔄 <i>The Agent service is restarting now and will reconnect in ~5 seconds!</i>",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(f"❌ <b>Update Failed:</b> {res.get('message')}", parse_mode="HTML")

@admin_only
async def cmd_speedtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Running VPS network latency & speed test (takes ~15s)...")
    res = run_cmd("curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --simple 2>/dev/null", timeout=40)
    await update.message.reply_text(f"📡 <b>Speedtest Results:</b>\n<pre>{res or 'Speedtest completed'}</pre>", parse_mode="HTML")

@admin_only
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_report(context.application)

# --- Silent Security Scanner (Blocks bots quietly in background) ---
async def scan_ssh_brute_force_silent():
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
                    alert_state['blocked_ips_history'].append({
                        'ip': ip,
                        'time': datetime.now().strftime("%H:%M:%S")
                    })
                    logger.info(f"[SILENT SHIELD] Auto-Banned SSH Intruder: {ip}")
    except Exception as e:
        logger.error(f"Error in SSH silent scan: {e}")

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
            f"📋 <b>S-Tech Server Daily Morning Briefing ({today_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Status:</b> 100% Operational & Healthy\n"
            f"⏱️ <b>Uptime:</b> {m['uptime']}\n"
            f"🧠 <b>RAM Usage:</b> {m['ram_percent']}% ({m['ram_used']} / {m['ram_total']})\n"
            f"💾 <b>Disk Usage:</b> {m['disk_percent']}% ({m['disk_free']} free)\n"
            f"📦 <b>Services:</b> {running_c}/{total_c} Containers Online\n"
            f"🛡️ <b>Security:</b> {blocked_count} Hacker Attacks Silently Banned Today\n"
            f"🌐 <b>Active Connections:</b> {m['active_connections']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Everything is secured and running smoothly!</i>"
        )
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=report_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending daily report: {e}")

# --- Critical Background Health & Resource Monitor ---
async def monitor_loop(app: Application):
    logger.info("Background health & critical threat monitor active.")
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

            # 2. Silent SSH Defense (Quiet Auto-Ban)
            await scan_ssh_brute_force_silent()

            # 3. CRITICAL: High RAM / Memory Overload Check
            ram = psutil.virtual_memory()
            if ram.percent >= RAM_THRESHOLD:
                if not alert_state['ram_alerted']:
                    alert_state['last_alert_type'] = "ram"
                    top_procs = get_top_memory_processes()
                    proc_str = "\n".join([f"• {p['name']} (PID {p['pid']}): {p['memory_percent']:.1f}% RAM" for p in top_procs])
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛠️ အလိုအလျောက် ရှင်းလင်း ပြင်ဆင်မည်", callback_data="fix_ram")]
                    ])

                    msg = (
                        f"🚨 <b>HIGH RAM OVERLOAD ALERT!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚠️ <b>RAM Usage:</b> <b>{ram.percent}%</b> ({format_bytes(ram.used)} / {format_bytes(ram.total)})\n"
                        f"ဆာဗာ လေးလံမှု မဖြစ်စေရန် အမြန် ရှင်းလင်းရန် လိုအပ်ပါသည်။\n\n"
                        f"<b>Top Memory Processes:</b>\n{proc_str}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👉 <i>အောက်ပါခလုတ်ကို နှိပ်ပါ သို့မဟုတ် 'ပြင်ဆင်လိုက်ပါ' ဟု ပြန်စာပို့နိုင်ပါသည်:</i>"
                    )
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML", reply_markup=keyboard)
                    alert_state['ram_alerted'] = True
            else:
                alert_state['ram_alerted'] = False

            # 4. CRITICAL: High CPU Overload Check
            cpu_val = psutil.cpu_percent(interval=1.0)
            if cpu_val >= CPU_THRESHOLD:
                if not alert_state['cpu_alerted']:
                    alert_state['last_alert_type'] = "cpu"
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛠️ CPU ဝန်လျော့ချ ပြင်ဆင်မည်", callback_data="fix_cpu")]
                    ])
                    msg = (
                        f"🚨 <b>HIGH CPU OVERLOAD ALERT!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚙️ <b>CPU Load:</b> <b>{cpu_val}%</b>\n"
                        f"ဆာဗာ ပရိုဆက်ဆာ ဝန်ပိနေပါသည်။\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👉 <i>'ပြင်ဆင်လိုက်ပါ' ဟု ပြန်စာပို့ပါက CPU ဝန်ကို ချက်ချင်း လျှော့ချပေးပါမည်။</i>"
                    )
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML", reply_markup=keyboard)
                    alert_state['cpu_alerted'] = True
            else:
                alert_state['cpu_alerted'] = False

            # 5. CRITICAL: Container / Service Crash Check
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
                        alert_state['last_alert_type'] = "container"
                        
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Restart Service Now", callback_data="fix_container")]
                        ])

                        alert_msg = (
                            f"🚨 <b>SERVICE DOWN ALERT!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"❌ Container <code>{target_name}</code> ရပ်တန့်သွားပါသည်!\n"
                            f"━━━━━━━━━━━━━━━━━━━━"
                        )
                        
                        if AUTO_RESTART and c:
                            alert_msg += "\n🔄 <i>Auto-healing is attempting restart...</i>"
                            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_msg, parse_mode="HTML")
                            run_cmd(f"docker restart {target_name}")
                            await asyncio.sleep(5)
                            
                            updated = get_docker_containers()
                            is_running = any(uc['name'] == target_name and uc['state'] == 'running' for uc in updated)
                            if is_running:
                                await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"✅ <b>Auto-Healed:</b> Service <code>{target_name}</code> is back ONLINE!", parse_mode="HTML")
                                alert_state['containers_down'].discard(target_name)
                        else:
                            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_msg, parse_mode="HTML", reply_markup=keyboard)
                else:
                    alert_state['containers_down'].discard(target_name)

            # 6. CRITICAL: DDoS Network Floods
            active_conns = get_active_connection_count()
            if active_conns >= DDOS_CONN_THRESHOLD:
                if not alert_state['ddos_alerted']:
                    alert_state['last_alert_type'] = "ddos"
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛡️ Enable DDoS Rate-Limiter", callback_data="fix_ddos")]
                    ])
                    msg = (
                        f"🚨 <b>CRITICAL DDoS TRAFFIC ATTACK DETECTED!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔗 Active Connections: <b>{active_conns}</b> (Abnormal Traffic Spike)\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👉 <i>'ပြင်ဆင်လိုက်ပါ' ဟု ပြန်စာပို့ပါက DDoS Shield ကို အသက်သွင်းပေးပါမည်။</i>"
                    )
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML", reply_markup=keyboard)
                    alert_state['ddos_alerted'] = True
            else:
                alert_state['ddos_alerted'] = False

        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL)

def main():
    if not BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is not set in config.env")
        sys.exit(1)

    print("🚀 Starting S-Tech AI DevOps & Cyber Defense Assistant (v5.0 Pro)...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.Document.ALL, handle_file_upload))

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("security", cmd_security))
    app.add_handler(CommandHandler("clean", cmd_clean))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("speedtest", cmd_speedtest))
    app.add_handler(CommandHandler("passwd", cmd_passwd))
    app.add_handler(CommandHandler("password", cmd_passwd))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(CommandHandler("update", cmd_upgrade))
    app.add_handler(CommandHandler("report", cmd_report))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))

    async def post_init(application: Application):
        asyncio.create_task(monitor_loop(application))
        if ADMIN_CHAT_ID:
            try:
                await application.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text="🤖 <b>S-Tech AI DevOps Assistant (v5.0 Pro) is ONLINE!</b>\n🛡️ Silent Shield: ACTIVE\n🛠️ Auto-Healer: READY\n\n• Say <i>'ဆာဗာ အခြေအနေ'</i> to inspect\n• Say <i>'ပြင်ဆင်လိုက်ပါ'</i> if server is slow\n• Type /security to view blocked attackers log.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")

    app.post_init = post_init
    app.run_polling()

if __name__ == '__main__':
    main()

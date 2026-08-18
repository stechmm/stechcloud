#!/usr/bin/env python3
"""
S-Tech VPS Server Maintenance & Cyber Defense AI Assistant (v3.0 - Full AI Brain Edition)
Author: Antigravity
Description: Powered by Google Gemini AI Brain with Function Calling, Cyber Intrusion Detection,
DDoS Spike Alerts, 24/7 Auto-Healing, and Natural Language Burmese/English Telegram Chat Assistant.
"""

import os
import sys
import time
import asyncio
import subprocess
import logging
import re
import json
from datetime import datetime
import psutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ContextTypes, filters
)

# Optional Gemini AI import
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
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '180')) # 3 mins
MONITORED_CONTAINERS = [c.strip() for c in os.getenv('MONITORED_CONTAINERS', 'personal-cloud-app,shadowbox,pos-server').split(',') if c.strip()]
AUTO_RESTART = os.getenv('AUTO_RESTART', 'True').lower() in ('true', '1', 'yes')

SSH_MAX_FAILED_ATTEMPTS = int(os.getenv('SSH_MAX_FAILED_ATTEMPTS', '4'))
DDOS_CONN_THRESHOLD = int(os.getenv('DDOS_CONN_THRESHOLD', '800'))

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('STechAIBrain')

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

def run_cmd(cmd, timeout=30):
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

# --- AI Tool Definitions (Callable by Gemini AI Brain) ---
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
    res = run_cmd(f"tar -czf {file_path} /root/personal-cloud/data /root/personal-cloud/storage 2>/dev/null || tar -czf {file_path} /root/stechcloud 2>/dev/null")
    if os.path.exists(file_path):
        return {"status": "success", "file": file_path, "size": format_bytes(os.path.getsize(file_path))}
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

def tool_run_safe_command(command: str):
    """Runs safe Linux diagnostic commands (e.g. df -h, free -m, top -b -n 1, netstat, etc.)."""
    # Guardrails against destructive commands
    forbidden = ["rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "chmod -R 777 /", "> /dev/sda", "shutdown"]
    for f in forbidden:
        if f in command.lower():
            return {"error": f"Security Block: Command '{command}' is prohibited by safety policy."}
    
    out = run_cmd(command, timeout=25)
    return {"command": command, "output": out}

# Initialize Gemini AI Model
ai_model = None
if GEMINI_AVAILABLE and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        tools_list = [
            tool_get_system_metrics,
            tool_manage_docker,
            tool_clean_cache,
            tool_backup_data,
            tool_manage_firewall,
            tool_run_speedtest,
            tool_run_safe_command
        ]
        
        system_instruction = (
            "You are S-Tech AI DevOps Engineer & Assistant - an intelligent, helpful, and highly capable server administrator AI for the owner's DigitalOcean VPS.\n"
            "You have direct access to tools to inspect CPU/RAM/Disk, restart containers, clean cache, backup files, and run safe commands.\n"
            "Rules:\n"
            "1. When the user asks anything about server health, status, or issues, ALWAYS use your tools first to get real data.\n"
            "2. Answer in natural, polite, and fluent Burmese (မြန်မာဘာသာ) unless the user asks in English.\n"
            "3. Format your answers cleanly with emojis, bullet points, and code blocks for readability on Telegram.\n"
            "4. Be proactive: If RAM or Disk is high, explain why and offer to clean cache.\n"
            "5. Always protect the server and never execute destructive wipe commands."
        )

        ai_model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            tools=tools_list,
            system_instruction=system_instruction
        )
        logger.info("Gemini AI Brain initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini AI: {e}")

# --- Natural Language Message Handler (AI Brain Chat) ---
@admin_only
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if not user_text:
        return

    # If Gemini is not configured, give a helpful prompt
    if not ai_model:
        await update.message.reply_text(
            "ℹ️ <b>AI Brain is not yet configured with Gemini API Key.</b>\n\n"
            "Please add your free <code>GEMINI_API_KEY</code> in <code>config.env</code> to chat in natural Burmese.\n"
            "In the meantime, you can use commands like /status, /containers, /clean, /backup, /security.",
            parse_mode="HTML"
        )
        return

    # Send typing action
    await update.message.chat.send_action("typing")

    try:
        # Start chat with automatic function calling enabled
        chat = ai_model.start_chat(enable_automatic_function_calling=True)
        response = await asyncio.to_thread(chat.send_message, user_text)
        reply_text = response.text or "အဆင်ပြေစွာ ဆောင်ရွက်ပြီးစီးပါပြီခင်ဗျာ။"
        await update.message.reply_text(reply_text)
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        await update.message.reply_text(f"⚠️ <b>AI Processing Error:</b> {str(e)}\n\nYou can still use manual commands: /status, /clean, /restart.", parse_mode="HTML")

# --- Bot Command Handlers ---

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 <b>Welcome to S-Tech AI DevOps & Cyber Defense Assistant (v3.0)</b>\n\n"
        "💬 <b>Natural AI Chat:</b> You can talk to me directly in Burmese or English! (e.g. <i>'ဆာဗာ အခြေအနေ ဘယ်လိုလဲ'</i> or <i>'RAM တွေရှင်းပေးပါ'</i>)\n\n"
        "<b>Direct Commands:</b>\n"
        "📊 /status - System metrics (CPU, RAM, Disk, Uptime)\n"
        "📦 /containers - Docker containers status\n"
        "🔄 /restart &lt;name&gt; - Restart a Docker container\n"
        "📜 /logs &lt;name&gt; - View container logs\n"
        "🧹 /clean - Clean unused cache & docker logs\n"
        "💾 /backup - Instant data archive backup\n"
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
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Creating backup archive...")
    res = tool_backup_data()
    if res.get('status') == 'success':
        await update.message.reply_text(f"✅ <b>Backup Created!</b>\n📁 File: <code>{res['file']}</code>\n📦 Size: {res['size']}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ Backup failed: {res.get('error')}")

@admin_only
async def cmd_speedtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Running VPS network latency & speed test (takes ~15s)...")
    res = tool_run_speedtest()
    await update.message.reply_text(f"📡 <b>Speedtest Results:</b>\n<pre>{res.get('speedtest_output')}</pre>", parse_mode="HTML")

@admin_only
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_report(context.application)

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

            # 6. Container Check & Auto-Restart
            containers = get_docker_containers()
            container_dict = {c['name']: c for c in containers}

            for target_name in MONITORED_CONTAINERS:
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

    print("🚀 Starting S-Tech AI DevOps & Cyber Defense Assistant (v3.0)...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Register Command Handlers
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
    app.add_handler(CommandHandler("reboot", cmd_reboot))

    # Natural Language AI Brain Chat Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))

    async def post_init(application: Application):
        asyncio.create_task(monitor_loop(application))
        if ADMIN_CHAT_ID:
            try:
                brain_status = "🧠 Gemini AI Brain: ACTIVATED" if ai_model else "⚙️ Command Mode Active (Add GEMINI_API_KEY for Natural Chat)"
                await application.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"🤖 <b>S-Tech AI DevOps Assistant is ONLINE!</b>\n{brain_status}\n\nType /status or send any message to chat.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")

    app.post_init = post_init
    app.run_polling()

if __name__ == '__main__':
    main()

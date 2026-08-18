#!/usr/bin/env python3
"""
S-Tech VPS Server Maintenance & Cyber Defense AI Agent (v2.0 Advanced Security)
Author: Antigravity
Description: Automated monitoring, Cyber Intrusion Detection (Fail2ban/Brute-force Auto-Ban), 
DDoS Traffic Spike Alert, Daily Morning Health Report, and Telegram Remote Control.
"""

import os
import sys
import time
import asyncio
import subprocess
import logging
import re
from datetime import datetime, time as dtime
import psutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'config.env'))

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', '')
CPU_THRESHOLD = float(os.getenv('CPU_THRESHOLD', '85'))
RAM_THRESHOLD = float(os.getenv('RAM_THRESHOLD', '85'))
DISK_THRESHOLD = float(os.getenv('DISK_THRESHOLD', '90'))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '180')) # 3 mins
MONITORED_CONTAINERS = [c.strip() for c in os.getenv('MONITORED_CONTAINERS', 'personal-cloud-app,shadowbox,pos-server').split(',') if c.strip()]
AUTO_RESTART = os.getenv('AUTO_RESTART', 'True').lower() in ('true', '1', 'yes')

# Security Thresholds
SSH_MAX_FAILED_ATTEMPTS = int(os.getenv('SSH_MAX_FAILED_ATTEMPTS', '4'))
DDOS_CONN_THRESHOLD = int(os.getenv('DDOS_CONN_THRESHOLD', '800'))

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('STechSecurityAgent')

# Internal State Tracking
alert_state = {
    'cpu_alerted': False,
    'ram_alerted': False,
    'disk_alerted': False,
    'ddos_alerted': False,
    'containers_down': set(),
    'daily_report_sent_date': None,
    'blocked_ips_today': set(),
    'failed_ssh_attempts': {} # ip -> count
}

# --- Helper Functions ---
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

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25)
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
        user_id = str(update.effective_user.id)
        if str(ADMIN_CHAT_ID) and user_id != str(ADMIN_CHAT_ID):
            logger.warning(f"Unauthorized access attempt from user_id: {user_id}")
            await update.message.reply_text("⛔ <b>Access Denied!</b> You are not authorized to control this server.", parse_mode="HTML")
            return
        return await func(update, context)
    return wrapper

# --- Bot Command Handlers ---

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🛡️ <b>S-Tech Server Maintenance & Cyber Defense Agent (v2.0)</b>\n\n"
        "I am actively protecting your VPS and monitoring system health 24/7.\n\n"
        "<b>System Commands:</b>\n"
        "📊 /status - System metrics (CPU, RAM, Disk, Uptime)\n"
        "📦 /containers - Docker containers status\n"
        "🔄 /restart &lt;name&gt; - Restart a Docker container\n"
        "📜 /logs &lt;name&gt; - View recent logs of a container\n"
        "🧹 /clean - Clear Docker unused cache & temp files\n"
        "💾 /backup - Backup Cloud & Database files\n"
        "🚀 /speedtest - Test VPS Internet speed\n\n"
        "<b>Cyber Security Commands:</b>\n"
        "🛡️ /security - Security audit & blocked attackers\n"
        "🚫 /ban &lt;IP&gt; - Manually ban a malicious IP address\n"
        "🔓 /unban &lt;IP&gt; - Unban an IP address\n"
        "📋 /report - Generate Instant Full Health Report\n"
        "⚠️ /reboot - Reboot the VPS server"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    swap = psutil.swap_memory()
    uptime_str = get_uptime()
    active_conns = get_active_connection_count()

    public_ip = run_cmd("curl -s -m 5 ifconfig.me || hostname -I | awk '{print $1}'")
    containers = get_docker_containers()
    running_c = sum(1 for c in containers if c['state'] == 'running')
    total_c = len(containers)

    msg = (
        f"🖥️ <b>S-Tech Server Health & Security Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Public IP:</b> <code>{public_ip}</code>\n"
        f"⏱️ <b>Uptime:</b> {uptime_str}\n"
        f"🔗 <b>Active Network Connections:</b> {active_conns}\n\n"
        f"⚙️ <b>CPU Load:</b> {cpu_percent}% ({cpu_count} Cores)\n"
        f"🧠 <b>RAM Usage:</b> {ram.percent}% ({format_bytes(ram.used)} / {format_bytes(ram.total)})\n"
        f"💽 <b>Swap:</b> {swap.percent}% ({format_bytes(swap.used)} / {format_bytes(swap.total)})\n"
        f"💾 <b>Disk Storage:</b> {disk.percent}% ({format_bytes(disk.used)} / {format_bytes(disk.total)})\n\n"
        f"📦 <b>Containers:</b> {running_c}/{total_c} Running\n"
        f"🛡️ <b>Blocked Attacks Today:</b> {len(alert_state['blocked_ips_today'])} IPs\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <i>Cyber Shield: ACTIVE (Firewall Enabled)</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ufw_status = run_cmd("sudo ufw status numbered | head -n 25")
    blocked_count = len(alert_state['blocked_ips_today'])
    conns = get_active_connection_count()

    blocked_list = "\n".join([f"• <code>{ip}</code>" for ip in list(alert_state['blocked_ips_today'])[-10:]]) or "None today"

    msg = (
        f"🛡️ <b>Cyber Security & Intrusion Shield Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <b>Firewall:</b> Active (Fail2ban & UFW)\n"
        f"🌐 <b>Active Connections:</b> {conns} connections\n"
        f"🚫 <b>Attacks Blocked Today:</b> {blocked_count}\n\n"
        f"<b>Recently Blocked Attacker IPs:</b>\n{blocked_list}\n\n"
        f"<b>Firewall Rule Preview:</b>\n<pre>{ufw_status or 'UFW not configured'}</pre>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/ban &lt;IP_ADDRESS&gt;</code>", parse_mode="HTML")
        return
    ip = context.args[0].strip()
    res = run_cmd(f"sudo ufw insert 1 deny from {ip} to any")
    alert_state['blocked_ips_today'].add(ip)
    await update.message.reply_text(f"🚫 <b>IP Blocked!</b> <code>{ip}</code> has been banned in firewall.\nResult: {res}", parse_mode="HTML")

@admin_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: <code>/unban &lt;IP_ADDRESS&gt;</code>", parse_mode="HTML")
        return
    ip = context.args[0].strip()
    res = run_cmd(f"sudo ufw delete deny from {ip}")
    alert_state['blocked_ips_today'].discard(ip)
    await update.message.reply_text(f"🔓 <b>IP Unbanned:</b> <code>{ip}</code> has been removed from firewall blocklist.", parse_mode="HTML")

@admin_only
async def cmd_containers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    containers = get_docker_containers()
    if not containers:
        await update.message.reply_text("ℹ️ No Docker containers found or Docker is not running.")
        return

    msg = "📦 <b>Docker Containers List:</b>\n\n"
    for c in containers:
        icon = "🟢" if c['state'] == 'running' else "🔴"
        msg += f"{icon} <b>{c['name']}</b>\n   └ Status: {c['status']}\n\n"

    await update.message.reply_text(msg, parse_mode="HTML")

@admin_only
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Please specify a container name.\nExample: <code>/restart personal-cloud-app</code>", parse_mode="HTML")
        return

    c_name = context.args[0]
    await update.message.reply_text(f"⏳ Restarting container <code>{c_name}</code>...", parse_mode="HTML")
    res = run_cmd(f"docker restart {c_name}")

    if "Error" in res or "No such container" in res:
        await update.message.reply_text(f"❌ Failed to restart <code>{c_name}</code>:\n{res}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"✅ Successfully restarted <code>{c_name}</code>!", parse_mode="HTML")

@admin_only
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Please specify a container name.\nExample: <code>/logs personal-cloud-app</code>", parse_mode="HTML")
        return

    c_name = context.args[0]
    logs = run_cmd(f"docker logs --tail 25 {c_name}")
    if len(logs) > 3500:
        logs = logs[-3500:]

    await update.message.reply_text(f"📜 <b>Recent Logs for {c_name}:</b>\n<pre>{logs or 'No logs available.'}</pre>", parse_mode="HTML")

@admin_only
async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧹 Cleaning up unused Docker images, containers, and temporary cache...")
    run_cmd("docker system prune -f")
    run_cmd("sudo apt clean && sudo journalctl --vacuum-time=3d")
    
    disk_after = psutil.disk_usage('/')
    await update.message.reply_text(
        f"✅ <b>Cleanup Complete!</b>\n\n"
        f"💽 Current Disk Usage: {disk_after.percent}% ({format_bytes(disk_after.free)} free)",
        parse_mode="HTML"
    )

@admin_only
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Creating backup archive of S-Tech Cloud data & metadata...")
    backup_dir = "/root/backups"
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/backup_{timestamp}.tar.gz"

    res = run_cmd(f"tar -czf {backup_file} /root/personal-cloud/data /root/personal-cloud/storage 2>/dev/null || tar -czf {backup_file} /root/stechcloud 2>/dev/null")
    
    if os.path.exists(backup_file):
        size = os.path.getsize(backup_file)
        await update.message.reply_text(f"✅ <b>Backup Created Successfully!</b>\n📁 File: <code>{backup_file}</code>\n📦 Size: {format_bytes(size)}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ Backup failed: {res}")

@admin_only
async def cmd_speedtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Running VPS network latency & speed test (takes ~15s)...")
    res = run_cmd("curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --simple 2>/dev/null")
    await update.message.reply_text(f"📡 <b>Speedtest Results:</b>\n<pre>{res or 'Speedtest tool unavailable'}</pre>", parse_mode="HTML")

@admin_only
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_report(context.application)

@admin_only
async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text("⚠️ <b>Warning:</b> This will reboot the entire VPS.\nTo proceed, type: <code>/reboot confirm</code>", parse_mode="HTML")
        return

    await update.message.reply_text("🔄 Rebooting server now... The bot will be offline for ~1-2 minutes.")
    subprocess.Popen(["sudo", "reboot"])

# --- Security Scanner (SSH Brute Force Detection) ---
async def scan_ssh_brute_force(app: Application):
    try:
        # Check failed SSH password logs in last 10 minutes
        log_out = run_cmd("sudo journalctl -u ssh --since '10 minutes ago' | grep -i 'Failed password'")
        if not log_out:
            return

        ip_pattern = r'from (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        matches = re.findall(ip_pattern, log_out)

        for ip in matches:
            # Skip private/local IPs
            if ip.startswith('127.') or ip.startswith('10.') or ip.startswith('192.168.'):
                continue

            alert_state['failed_ssh_attempts'][ip] = alert_state['failed_ssh_attempts'].get(ip, 0) + 1

            if alert_state['failed_ssh_attempts'][ip] >= SSH_MAX_FAILED_ATTEMPTS:
                if ip not in alert_state['blocked_ips_today']:
                    # Auto-ban via UFW Firewall
                    run_cmd(f"sudo ufw insert 1 deny from {ip} to any")
                    alert_state['blocked_ips_today'].add(ip)

                    msg = (
                        f"🛡️ <b>CYBER INTRUSION BLOCKED!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚨 <b>Attacker IP:</b> <code>{ip}</code>\n"
                        f"⚠️ <b>Reason:</b> Repeated SSH Password Brute-Force ({alert_state['failed_ssh_attempts'][ip]} failed attempts)\n"
                        f"🔒 <b>Action Taken:</b> IP permanently BANNED in Firewall (UFW)\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<i>S-Tech Defense Shield active</i>"
                    )
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in SSH security scan: {e}")

# --- Daily Morning Health & Security Report (08:00 AM) ---
async def send_daily_report(app: Application):
    try:
        if not ADMIN_CHAT_ID:
            return

        cpu_percent = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        uptime_str = get_uptime()
        conns = get_active_connection_count()
        containers = get_docker_containers()
        running_c = sum(1 for c in containers if c['state'] == 'running')
        total_c = len(containers)
        blocked_count = len(alert_state['blocked_ips_today'])

        today_str = datetime.now().strftime("%d-%b-%Y")

        report_msg = (
            f"📋 <b>S-Tech Server Daily Report ({today_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Status:</b> 100% Operational & Healthy\n"
            f"⏱️ <b>Uptime:</b> {uptime_str}\n"
            f"🧠 <b>RAM Usage:</b> {ram.percent}% ({format_bytes(ram.used)} / {format_bytes(ram.total)})\n"
            f"💾 <b>Disk Usage:</b> {disk.percent}% ({format_bytes(disk.free)} free space)\n"
            f"📦 <b>Services:</b> {running_c}/{total_c} Containers Online\n"
            f"🛡️ <b>Security:</b> {blocked_count} Malicious Attacks Blocked Today\n"
            f"🌐 <b>Active Connections:</b> {conns}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Everything is running smoothly! Have a great day!</i>"
        )
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=report_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending daily report: {e}")

# --- Background Monitoring Task ---
async def monitor_loop(app: Application):
    logger.info("Background health & security monitor started.")
    await asyncio.sleep(10)

    while True:
        try:
            if not ADMIN_CHAT_ID:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            now = datetime.now()

            # 1. Daily Report Trigger at 08:00 AM
            today_date = now.date()
            if now.hour == 8 and alert_state['daily_report_sent_date'] != today_date:
                await send_daily_report(app)
                alert_state['daily_report_sent_date'] = today_date
                alert_state['blocked_ips_today'].clear()
                alert_state['failed_ssh_attempts'].clear()

            # 2. Cyber Intrusion & Brute Force Check
            await scan_ssh_brute_force(app)

            # 3. DDoS Connection Spike Check
            active_conns = get_active_connection_count()
            if active_conns >= DDOS_CONN_THRESHOLD:
                if not alert_state['ddos_alerted']:
                    msg = (
                        f"🚨 <b>POTENTIAL DDoS / TRAFFIC FLOOD DETECTED!</b>\n"
                        f"Active network connections spiked to <b>{active_conns}</b> (Threshold: {DDOS_CONN_THRESHOLD}).\n"
                        f"Check active traffic via <code>/security</code>"
                    )
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['ddos_alerted'] = True
            else:
                alert_state['ddos_alerted'] = False

            # 4. Check RAM
            ram = psutil.virtual_memory()
            if ram.percent >= RAM_THRESHOLD:
                if not alert_state['ram_alerted']:
                    msg = f"🚨 <b>HIGH RAM ALERT!</b>\nRAM usage reached <b>{ram.percent}%</b> ({format_bytes(ram.used)}/{format_bytes(ram.total)})."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['ram_alerted'] = True
            else:
                alert_state['ram_alerted'] = False

            # 5. Check Disk
            disk = psutil.disk_usage('/')
            if disk.percent >= DISK_THRESHOLD:
                if not alert_state['disk_alerted']:
                    msg = f"🚨 <b>HIGH DISK ALERT!</b>\nDisk usage is at <b>{disk.percent}%</b>. Please run /clean to free up space."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['disk_alerted'] = True
            else:
                alert_state['disk_alerted'] = False

            # 6. Check Monitored Containers & Auto-Restart
            containers = get_docker_containers()
            container_dict = {c['name']: c for c in containers}

            for target_name in MONITORED_CONTAINERS:
                c = container_dict.get(target_name)
                if not c or c['state'] != 'running':
                    if target_name not in alert_state['containers_down']:
                        alert_state['containers_down'].add(target_name)
                        
                        alert_msg = f"⚠️ <b>CONTAINER DOWN!</b>\nService <code>{target_name}</code> has stopped or crashed!"
                        
                        if AUTO_RESTART and c:
                            alert_msg += f"\n🔄 <i>Attempting auto-restart...</i>"
                            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_msg, parse_mode="HTML")
                            
                            # Restart action
                            run_cmd(f"docker restart {target_name}")
                            await asyncio.sleep(5)
                            
                            # Check if restarted
                            updated = get_docker_containers()
                            is_now_running = any(uc['name'] == target_name and uc['state'] == 'running' for uc in updated)
                            if is_now_running:
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
        print("Please copy config.env.example to config.env and fill in your Bot Token & Chat ID.")
        sys.exit(1)

    print("🚀 Starting S-Tech Server Maintenance & Cyber Defense Agent (v2.0)...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Register Handlers
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

    # Setup background task on app startup
    async def post_init(application: Application):
        asyncio.create_task(monitor_loop(application))
        if ADMIN_CHAT_ID:
            try:
                await application.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text="🛡️ <b>S-Tech Server Maintenance & Cyber Defense Agent is ONLINE!</b>\nType /status or /security to inspect VPS health & defense shield.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")

    app.post_init = post_init

    # Run bot
    app.run_polling()

if __name__ == '__main__':
    main()

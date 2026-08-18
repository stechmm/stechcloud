#!/usr/bin/env python3
"""
S-Tech VPS Server Maintenance AI Agent
Author: Antigravity
Description: Automated monitoring, health alerts, container auto-healing, and Telegram remote control bot.
"""

import os
import sys
import time
import asyncio
import subprocess
import logging
from datetime import datetime, timedelta
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
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))
MONITORED_CONTAINERS = [c.strip() for c in os.getenv('MONITORED_CONTAINERS', 'personal-cloud-app,shadowbox').split(',') if c.strip()]
AUTO_RESTART = os.getenv('AUTO_RESTART', 'True').lower() in ('true', '1', 'yes')

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('STechAgent')

# State tracker for alerts to avoid spamming
alert_state = {
    'cpu_alerted': False,
    'ram_alerted': False,
    'disk_alerted': False,
    'containers_down': set()
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
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
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
        "🤖 <b>Welcome to S-Tech Server Maintenance Agent!</b>\n\n"
        "I am actively monitoring your VPS health and containers.\n\n"
        "<b>Available Commands:</b>\n"
        "📊 /status - System metrics (CPU, RAM, Disk, Uptime)\n"
        "📦 /containers - Docker containers status\n"
        "🔄 /restart &lt;name&gt; - Restart a Docker container\n"
        "📜 /logs &lt;name&gt; - View recent logs of a container\n"
        "🧹 /clean - Clear Docker unused cache & temp files\n"
        "💾 /backup - Backup Cloud & Database files\n"
        "🚀 /speedtest - Test VPS Internet speed\n"
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

    # Get IP Address
    public_ip = run_cmd("curl -s -m 5 ifconfig.me || hostname -I | awk '{print $1}'")

    # Containers summary
    containers = get_docker_containers()
    running_c = sum(1 for c in containers if c['state'] == 'running')
    total_c = len(containers)

    msg = (
        f"🖥️ <b>S-Tech Server Health Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>IP Address:</b> <code>{public_ip}</code>\n"
        f"⏱️ <b>Uptime:</b> {uptime_str}\n\n"
        f"⚙️ <b>CPU:</b> {cpu_percent}% ({cpu_count} Cores)\n"
        f"🧠 <b>RAM:</b> {ram.percent}% ({format_bytes(ram.used)} / {format_bytes(ram.total)})\n"
        f"💽 <b>Swap:</b> {swap.percent}% ({format_bytes(swap.used)} / {format_bytes(swap.total)})\n"
        f"💾 <b>Disk (/):</b> {disk.percent}% ({format_bytes(disk.used)} / {format_bytes(disk.total)})\n\n"
        f"📦 <b>Containers:</b> {running_c}/{total_c} Running\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <i>Status: All systems operational</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

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
    prune_res = run_cmd("docker system prune -f")
    apt_res = run_cmd("sudo apt clean && sudo journalctl --vacuum-time=3d")
    
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

    # Archive data
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
async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text("⚠️ <b>Warning:</b> This will reboot the entire VPS.\nTo proceed, type: <code>/reboot confirm</code>", parse_mode="HTML")
        return

    await update.message.reply_text("🔄 Rebooting server now... The bot will be offline for ~1-2 minutes.")
    subprocess.Popen(["sudo", "reboot"])

# --- Background Monitoring Task ---
async def monitor_loop(app: Application):
    logger.info("Background health monitor started.")
    await asyncio.sleep(10)  # Initial grace delay

    while True:
        try:
            if not ADMIN_CHAT_ID:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # 1. Check RAM
            ram = psutil.virtual_memory()
            if ram.percent >= RAM_THRESHOLD:
                if not alert_state['ram_alerted']:
                    msg = f"🚨 <b>HIGH RAM ALERT!</b>\nRAM usage reached <b>{ram.percent}%</b> ({format_bytes(ram.used)}/{format_bytes(ram.total)})."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['ram_alerted'] = True
            else:
                alert_state['ram_alerted'] = False

            # 2. Check Disk
            disk = psutil.disk_usage('/')
            if disk.percent >= DISK_THRESHOLD:
                if not alert_state['disk_alerted']:
                    msg = f"🚨 <b>HIGH DISK ALERT!</b>\nDisk usage is at <b>{disk.percent}%</b>. Please run /clean to free up space."
                    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                    alert_state['disk_alerted'] = True
            else:
                alert_state['disk_alerted'] = False

            # 3. Check Monitored Containers & Auto-Restart
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

    print("🚀 Starting S-Tech Server Maintenance Agent...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Register Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
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
                    text="🤖 <b>S-Tech Server Maintenance Agent is now ONLINE!</b>\nType /status to inspect VPS health.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")

    app.post_init = post_init

    # Run bot
    app.run_polling()

if __name__ == '__main__':
    main()

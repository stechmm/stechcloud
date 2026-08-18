# 🤖 S-Tech VPS Server Maintenance AI Agent

DigitalOcean VPS ပေါ်ရှိ **S-Tech Cloud, POS Server, Outline VPN** စသည်တို့ကို ၂၄ နာရီပတ်လုံး အလိုအလျောက် စောင့်ကြည့်ပြီး Telegram မှတစ်ဆင့် အလွယ်တကူ ထိန်းချုပ်ခိုင်းစေနိုင်မည့် **AI Maintenance Agent** ဖြစ်ပါသည်။

---

## 🌟 အဓိက လုပ်ဆောင်ချက်များ (Features)

1. **🚨 Real-Time Health Alerts (အလိုအလျောက် သတိပေးခြင်း):**
   - RAM သို့မဟုတ် Disk ပြည့်လုနီးပါးဖြစ်လျှင် (ဥပမာ > 85%) Telegram သို့ ချက်ချင်း Alert ပို့ပေးခြင်း။
   - S-Tech Cloud သို့မဟုတ် POS Container ကျသွားပါက ချက်ချင်း သတိပေးခြင်း။
2. **🔄 Container Auto-Healing (အလိုအလျောက် ပြန်ဖွင့်ပေးခြင်း):**
   - Container တစ်ခုခု Crash ဖြစ်သွားပါက လူကိုယ်တိုင် ဝင်စရာမလိုဘဲ Agent က အလိုအလျောက် `docker restart` ပြုလုပ်ပေးခြင်း။
3. **📱 Telegram Remote Control (ဖုန်းမှ လှမ်းခိုင်းနိုင်သော Command များ):**
   - `/status` - CPU, RAM, Disk, Uptime နှင့် IP Status စစ်ဆေးခြင်း။
   - `/containers` - Docker containers အားလုံး၏ အခြေအနေကို ကြည့်ရှုခြင်း။
   - `/restart <name>` - Container တစ်ခုကို လှမ်း၍ Restart ချခြင်း။
   - `/logs <name>` - Container ၏ နောက်ဆုံး Error logs များကို ဖတ်ရှုခြင်း။
   - `/clean` - မလိုအပ်သော Docker images, temp logs များကို ရှင်းထုတ်ပြီး Disk နေရာချဲ့ခြင်း။
   - `/backup` - Cloud Data နှင့် Database များကို Archive backup ဆွဲခြင်း။
   - `/speedtest` - VPS ၏ အင်တာနက် Speed ကို စစ်ဆေးခြင်း။
   - `/reboot confirm` - VPS Server တစ်ခုလုံးကို လှမ်း၍ Restart ချခြင်း။
4. **🔒 Admin Whitelist Security:**
   - သတ်မှတ်ထားသော Owner (Admin) ၏ Telegram ID မှသာ Command ပေးခိုင်းနိုင်ပြီး သူစိမ်းများ ခိုင်းခွင့်မရှိအောင် ကာကွယ်ထားခြင်း။

---

## 🚀 Setup လုပ်နည်း (၁ မိနစ်အတွင်း)

### အဆင့် (၁) - Telegram Bot Token နှင့် Chat ID ရယူခြင်း
1. Telegram တွင် **[@BotFather](https://t.me/BotFather)** ထံသို့ မက်ဆေ့ခ်ျပို့ပြီး `/newbot` ဖြင့် Bot တစ်ခုဆောက်ကာ **API TOKEN** ကို ယူပါ။
2. Telegram တွင် **[@userinfobot](https://t.me/userinfobot)** ထံသို့ မက်ဆေ့ခ်ျပို့ပြီး မိမိ၏ **Numeric ID (ဥပမာ `123456789`)** ကို ရယူပါ။

---

### အဆင့် (၂) - VPS ပေါ်တွင် Agent သွင်းခြင်း

```bash
# ၁။ Agent folder ထဲသို့ ဝင်ပါ
cd ~/stechcloud/agent

# ၂။ Installer script ကို run ပါ
chmod +x install-agent.sh
./install-agent.sh

# ၃။ Bot Token နှင့် Chat ID ထည့်ပါ
nano config.env
```

`config.env` ထဲတွင် အောက်ပါအတိုင်း ဖြည့်စွက်ပါ:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
ADMIN_CHAT_ID=123456789
```

---

### အဆင့် (၃) - Agent စတင် Run ခြင်း

```bash
# Agent ကို Background Service အဖြစ် စတင် Run ပါ
sudo systemctl start stech-agent

# အလုပ်လုပ်နေမှု အခြေအနေ စစ်ဆေးရန်
sudo systemctl status stech-agent
```

ယခုဆိုလျှင် သင်၏ Telegram Bot ထဲသို့ ဝင်ရောက်ပြီး **`/status`** ဟု ပို့ရုံဖြင့် Server Health ကို ဖုန်းထဲမှ စတင် ထိန်းချုပ်စောင့်ကြည့်နိုင်ပါပြီ!

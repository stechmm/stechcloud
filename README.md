# ☁️ Personal Cloud Storage (ကိုယ်ပိုင် Cloud စနစ်)

ဖုန်း (iOS / Android)၊ တက်ဘလက် (iPad / Tablet) နှင့် ကွန်ပျူတာ (Windows / Mac / Linux) တို့မှ လွယ်ကူစွာ ဖိုင်များ တင်ခြင်း၊ ဒေါင်းခြင်း၊ Media Streaming ကြည့်ရှုခြင်းနှင့် Link ဖြင့် မျှဝေခြင်းများ ပြုလုပ်နိုင်သော Self-Hosted Personal Cloud Storage စနစ် ဖြစ်ပါသည်။

---

## 🌟 အဓိက Feature များ (Key Features)

1. **Cross-Platform Responsive Web & PWA:**
   - ဖုန်းနှင့် တက်ဘလက်များတွင် Native App ကဲ့သို့ Home Screen တွင် Add to Home screen ပြုလုပ်၍ အသုံးပြုနိုင်ခြင်း။
2. **File & Folder Management:**
   - Multi-file Upload, Drag & Drop, Folder အလိုက် Upload တင်နိုင်ခြင်း။
   - Folder အသစ်ဆောက်ခြင်း၊ နာမည်ပြောင်းခြင်း၊ အကြိုက်ဆုံး (Favorites / Starred) သတ်မှတ်ခြင်း။
3. **Built-in Media Previewers & Streaming:**
   - **Photos:** Gallery ကြည့်ရှုနိုင်ခြင်း။
   - **Videos:** 4K/1080p Video များကို အချိန်ဆွဲစရာမလိုဘဲ တိုက်ရိုက် Stream လုပ်၍ ကြည့်ရှုနိုင်ခြင်း (HTTP Byte Range Support)။
   - **Music / Audio:** သီချင်းများ တိုက်ရိုက် နားဆင်နိုင်ခြင်း။
   - **Documents & Code:** PDF, TXT, MD, Code ဖိုင်များကို Browser ထဲတွင် တိုက်ရိုက် ဖတ်ရှုနိုင်ခြင်း။
4. **Recycle Bin (Trash):**
   - မတော်တဆ ဖျက်မိသော ဖိုင်များကို ပြန်လည် ဆယ်ယူနိုင်ခြင်း (Restore) သို့မဟုတ် အပြီးတိုင် ဖျက်ထုတ်နိုင်ခြင်း။
5. **Public Share Links:**
   - ဖိုင်များကို မည်သူ့ကိုမဆို Link ပေး၍ ဒေါင်းလုဒ်ဆွဲခွင့် ပြုနိုင်ခြင်း (Password ခံထားနိုင်ပြီး Expire ဖြစ်မည့်ရက် သတ်မှတ်နိုင်သည်)။
6. **Batch Operations:**
   - ဖိုင် အများအပြားကို တစ်ပြိုင်နက် ရွေးချယ်၍ ZIP ဖိုင်အဖြစ် ဒေါင်းလုဒ်ဆွဲခြင်း၊ တစ်ပြိုင်နက် ဖျက်ခြင်း။
7. **Storage Meter:**
   - မိမိ VPS တွင် Data မည်မျှ အသုံးပြုထားသည်ကို စောင့်ကြည့်နိုင်ခြင်း။

---

## 🚀 DigitalOcean VPS ပေါ်တွင် Setup လုပ်နည်း

### နည်းလမ်း (၁) - Docker Compose ဖြင့် ၁-မိနစ်အတွင်း တင်နည်း (အလွယ်ဆုံး)

1. **DigitalOcean Droplet (Ubuntu 22.04 / 24.04)** သို့ SSH ဖြင့် ဝင်ပါ-
   ```bash
   ssh root@<YOUR_VPS_IP>
   ```

2. **Project folder ဆောက်ပြီး code များ ကူးထည့်ပါ** (သို့မဟုတ် Git clone လုပ်ပါ)-
   ```bash
   mkdir -p ~/personal-cloud && cd ~/personal-cloud
   ```

3. **`deploy.sh` script ကို run ပါ**-
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

4. အားလုံးပြီးပါက Browser မှ `http://<YOUR_VPS_IP>:3000` သို့ ဝင်ရောက်ပြီး Master Password `admin123` ဖြင့် စတင် အသုံးပြုနိုင်ပါပြီ။

---

### နည်းလမ်း (၂) - Node.js ဖြင့် တိုက်ရိုက် Run နည်း

```bash
# Node.js 20 သွင်းခြင်း
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Dependencies သွင်းခြင်း
cd personal-cloud
npm install

# PM2 ဖြင့် Background တွင် အမြဲ Run ထားရန်
sudo npm install -g pm2
pm2 start server.js --name "my-cloud"
pm2 startup
pm2 save
```

---

## 🔒 Domain Name နှင့် Free SSL (HTTPS) ချိတ်ဆက်နည်း (Recommended)

ဖုန်းနှင့် PC ကနေ `https://cloud.yourdomain.com` ဖြင့် လုံခြုံစွာ သုံးနိုင်ရန် Nginx Reverse Proxy နှင့် Let's Encrypt SSL ထည့်နည်း-

```bash
# Nginx နှင့် Certbot သွင်းခြင်း
sudo apt install -y nginx certbot python3-certbot-nginx

# Nginx config ပြင်ဆင်ခြင်း
sudo nano /etc/nginx/sites-available/cloud
```

အောက်ပါ config ကို ထည့်ပါ-
```nginx
server {
    server_name cloud.yourdomain.com;

    client_max_body_size 10G; # 10GB အထိ ဖိုင်တင်ခွင့်ပြုရန်

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable လုပ်ပြီး SSL ထည့်ပါ-
```bash
sudo ln -s /etc/nginx/sites-available/cloud /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Free SSL ရယူခြင်း
sudo certbot --nginx -d cloud.yourdomain.com
```

---

## 📱 ဖုန်းနှင့် Tablet တွင် App ကဲ့သို့ သုံးနည်း (PWA)
1. ဖုန်း Browser (Chrome / Safari) တွင် မိမိ Cloud URL သို့ ဝင်ပါ။
2. Browser menu (အစက် ၃ စက် သို့မဟုတ် Share icon) ကို နှိပ်ပြီး **"Add to Home Screen" (သို့မဟုတ် "Install App")** ကို နှိပ်ပါ။
3. ဖုန်း Screen ပေါ်တွင် App icon အဖြစ် ပေါ်လာမည်ဖြစ်ပြီး Fullscreen ဖြင့် အသုံးပြုနိုင်ပါသည်။

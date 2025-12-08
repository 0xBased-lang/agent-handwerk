# 🚀 Quick Deployment to Contabo VPS

**Everything is ready to deploy!** This guide gets you from zero to production in ~30 minutes.

## What You're Deploying

✅ **Web Chat** - Customer intake with German LLM
✅ **Admin Dashboard** - Job management interface
✅ **Job Management API** - 13 REST endpoints
✅ **Database** - PostgreSQL with auto-migrations
✅ **Nginx** - Reverse proxy with SSL ready

## Prerequisites

Before starting, have ready:

- [ ] Contabo VPS IP address
- [ ] Domain name (e.g., `handwerk.your-domain.com`)
- [ ] DNS configured (A record: `handwerk.your-domain.com` → VPS IP)
- [ ] GROQ API key (free at https://console.groq.com/)
- [ ] 30 minutes of time

## Step-by-Step Deployment

### Step 1: SSH into Contabo (2 min)

```bash
# From your local machine
ssh root@YOUR_CONTABO_IP
```

### Step 2: Install Dependencies (5 min)

```bash
# Update system
apt update && apt upgrade -y

# Install everything needed
apt install -y \
  python3.11 \
  python3.11-venv \
  python3-pip \
  nginx \
  postgresql \
  postgresql-contrib \
  certbot \
  python3-certbot-nginx \
  git

# Verify installations
python3.11 --version  # Should show 3.11+
nginx -v              # Should show nginx
psql --version        # Should show PostgreSQL
```

### Step 3: Setup Database (3 min)

```bash
# Create database
sudo -u postgres psql << 'EOF'
CREATE DATABASE phone_agent;
CREATE USER phone_agent_user WITH ENCRYPTED PASSWORD 'YourSecurePassword123!';
GRANT ALL PRIVILEGES ON DATABASE phone_agent TO phone_agent_user;
\q
EOF

# Test connection
sudo -u postgres psql -d phone_agent -c "\dt"
```

### Step 4: Deploy Code (5 min)

**Option A: Upload from Local**

```bash
# From your local machine (in a new terminal)
cd ~/Desktop/IT-Friends/solutions/phone-agent

# Upload to VPS
rsync -avz --exclude 'venv' --exclude '*.pyc' --exclude '__pycache__' --exclude 'models' \
  . root@YOUR_CONTABO_IP:/opt/phone-agent/

# Back to VPS terminal
cd /opt/phone-agent
```

**Option B: Git Clone** (if you have a repo)

```bash
# On VPS
mkdir -p /opt
cd /opt
git clone https://github.com/YOUR-USERNAME/phone-agent.git
cd phone-agent
```

### Step 5: Configure Environment (3 min)

```bash
# On VPS, create .env file
cd /opt/phone-agent
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://phone_agent_user:YourSecurePassword123!@localhost/phone_agent

# Server
ITF_ENVIRONMENT=production
ITF_LOG_LEVEL=INFO
ITF_DEVICE_ID=contabo-vps-1

# AI (use cloud instead of local models)
GROQ_API_KEY=YOUR_GROQ_API_KEY_HERE

# Domain
ITF_DOMAIN=handwerk.your-domain.com
EOF

# Secure it
chmod 600 .env
```

**⚠️ IMPORTANT**: Replace `YOUR_GROQ_API_KEY_HERE` with your actual Groq API key!

### Step 6: Run Deployment Script (5 min)

```bash
# On VPS
cd /opt/phone-agent
chmod +x deploy/deploy.sh

# Deploy!
sudo ./deploy/deploy.sh
```

**This will**:
- Create Python virtual environment
- Install all dependencies
- Run database migrations
- Create systemd service
- Start the application

**Expected output**:
```
[✓] Creating directories...
[✓] Setting up Python virtual environment...
[✓] Installing dependencies...
[✓] Running database migrations...
[✓] Installing systemd service...
[✓] Enabling and starting service...
[✓] Service started successfully!

=== Deployment Complete ===

Service status: active
Access the demo at: http://YOUR_IP:8080/demo/handwerk
```

### Step 7: Configure Nginx (5 min)

```bash
# On VPS
# Copy nginx config
cp /opt/phone-agent/deploy/nginx/phone-agent.conf /etc/nginx/sites-available/phone-agent

# Edit to add your domain
nano /etc/nginx/sites-available/phone-agent
# Change line 11: server_name handwerk.your-domain.com;

# Enable site
ln -s /etc/nginx/sites-available/phone-agent /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test config
nginx -t

# If test passes, restart
systemctl restart nginx
```

### Step 8: Setup SSL (2 min)

```bash
# On VPS
certbot --nginx -d handwerk.your-domain.com

# Follow the prompts:
# 1. Enter your email
# 2. Agree to terms (Y)
# 3. Share email? (optional)
# 4. Redirect HTTP to HTTPS? (2 - Yes)
```

**Certbot will**:
- Get SSL certificate from Let's Encrypt
- Automatically configure Nginx for HTTPS
- Set up auto-renewal (certificate renews every 90 days)

### Step 9: Test Everything (5 min)

```bash
# Check service
systemctl status phone-agent

# Check logs
journalctl -u phone-agent -n 50

# Test health endpoint
curl https://handwerk.your-domain.com/health

# Should return: {"status":"healthy","version":"0.1.0"}
```

**Test in Browser**:

1. **Web Chat**: `https://handwerk.your-domain.com/static/chat.html`
   - Type: "Meine Heizung ist ausgefallen!"
   - Verify: Bot responds in German
   - Complete chat → Job created

2. **Admin Dashboard**: `https://handwerk.your-domain.com/static/admin.html`
   - Should see: Statistics cards
   - Should see: Job you just created
   - Click: "📅 Planen" → Status changes

3. **API Docs**: `https://handwerk.your-domain.com/docs`
   - Should see: FastAPI interactive docs
   - Try: `GET /api/v1/jobs/stats`

## ✅ Success Checklist

Deployment succeeded if:

- [ ] `systemctl status phone-agent` shows "active (running)"
- [ ] `curl https://your-domain.com/health` returns `{"status":"healthy"}`
- [ ] Web chat loads and responds in German
- [ ] Admin dashboard shows job statistics
- [ ] Jobs created via chat appear in admin
- [ ] HTTPS works (green padlock in browser)
- [ ] No errors in logs: `journalctl -u phone-agent -n 100`

## 🔐 Secure Admin Dashboard (Important!)

The admin dashboard currently has **no authentication**. Add it now:

```bash
# Install password tool
apt install apache2-utils

# Create admin password
htpasswd -c /etc/nginx/.htpasswd admin
# Enter a secure password when prompted

# Update nginx config
nano /etc/nginx/sites-available/phone-agent

# Add before the last } in the server block:
    location /static/admin.html {
        auth_basic "Admin Area";
        auth_basic_user_file /etc/nginx/.htpasswd;
        alias /opt/phone-agent/static/admin.html;
    }

# Restart nginx
systemctl restart nginx
```

Now admin requires username: `admin` + password you set.

## 🔄 Daily Operations

### View Logs
```bash
# Real-time logs
journalctl -u phone-agent -f

# Last 100 lines
journalctl -u phone-agent -n 100

# Errors only
journalctl -u phone-agent -p err
```

### Restart Service
```bash
systemctl restart phone-agent
systemctl status phone-agent
```

### Update Code
```bash
cd /opt/phone-agent
git pull  # Or rsync from local
systemctl restart phone-agent
```

### Backup Database
```bash
# Manual backup
sudo -u postgres pg_dump phone_agent | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore if needed
gunzip -c backup_20250108.sql.gz | sudo -u postgres psql phone_agent
```

## 🆘 Troubleshooting

### Service won't start

```bash
# Check logs
journalctl -u phone-agent -n 50

# Common issues:
# 1. Database connection failed
sudo -u postgres psql -d phone_agent -c "SELECT 1"

# 2. Port 8080 already in use
lsof -i :8080

# 3. Python dependencies missing
cd /opt/phone-agent
./venv/bin/pip install -e ".[dev]"
```

### Nginx 502 Bad Gateway

```bash
# Check if service is running
systemctl status phone-agent

# Check if port 8080 is listening
ss -tlnp | grep 8080

# Restart both
systemctl restart phone-agent
systemctl restart nginx
```

### Can't access from outside

```bash
# Check firewall
ufw status

# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Check nginx is running
systemctl status nginx
```

### Jobs not appearing in dashboard

```bash
# Check database
sudo -u postgres psql phone_agent
SELECT COUNT(*) FROM jobs;
\q

# Check API
curl http://localhost:8080/api/v1/jobs/stats

# If 0 jobs, create one via chat
```

## 📊 Monitoring

### System Resources

```bash
# CPU/Memory
htop

# Disk space
df -h

# Network
iftop  # Install: apt install iftop
```

### Application Metrics

```bash
# Active connections
ss -s

# Request logs
tail -f /var/log/nginx/phone-agent.access.log

# Error logs
tail -f /var/log/nginx/phone-agent.error.log
```

## 🎉 You're Done!

Your Handwerk Phone Agent is now live at:

- 💬 **Web Chat**: `https://handwerk.your-domain.com/static/chat.html`
- 📊 **Admin**: `https://handwerk.your-domain.com/static/admin.html`
- 📚 **API Docs**: `https://handwerk.your-domain.com/docs`
- ❤️ **Health**: `https://handwerk.your-domain.com/health`

**Share with customers**: `https://handwerk.your-domain.com/static/chat.html`

---

## 📚 Additional Documentation

- **Full Deployment Guide**: `docs/DEPLOYMENT.md`
- **New Features Guide**: `docs/DEPLOYMENT_UPDATE_HANDWERK.md`
- **Admin Dashboard**: `docs/ADMIN_DASHBOARD.md`
- **LLM Integration**: `docs/LLM_CHAT_INTEGRATION.md`

**Need help?** Check the troubleshooting sections in the docs above!

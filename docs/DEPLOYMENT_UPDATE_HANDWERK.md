# Deployment Update: Handwerk Web Features

## 🎯 New Features Added Today

This guide covers deploying the NEW features added to the Phone Agent:

| Feature | Status | Files Affected |
|---------|--------|----------------|
| **Web Chat with LLM** | ✅ Ready | `static/chat.html`, `api/chat_websocket.py` |
| **Job Management API** | ✅ Ready | `api/jobs.py` (13 endpoints) |
| **Admin Dashboard** | ✅ Ready | `static/admin.html` |
| **Job Repository** | ✅ Ready | `db/repositories/jobs.py` |
| **Handwerk Service** | ✅ Ready | `services/handwerk_service.py` |

## ✅ What's Already Configured

Your existing deployment infrastructure (`deploy/`) already has:

- ✅ **Systemd Service** - `deploy/systemd/phone-agent.service`
- ✅ **Nginx Config** - `deploy/nginx/phone-agent.conf`
- ✅ **Deployment Script** - `deploy/deploy.sh`
- ✅ **Docker Deployment** - `deploy/docker-deploy.sh`
- ✅ **Ansible Playbook** - `infrastructure/ansible/playbooks/deploy-phone-agent.yml`

**Good News**: No changes needed to existing deployment files! The new features work with your existing setup.

## 🚀 Deployment Checklist for Contabo VPS

### Step 1: Prepare Contabo VPS

```bash
# SSH into your Contabo VPS
ssh root@your-contabo-ip

# Update system
apt update && apt upgrade -y

# Install dependencies
apt install -y python3.11 python3.11-venv nginx postgresql certbot python3-certbot-nginx

# Create deployment directory
mkdir -p /opt/phone-agent
```

### Step 2: Upload Code to VPS

**Option A: Git (Recommended)**
```bash
# On VPS
cd /opt/phone-agent
git clone https://github.com/YOUR-REPO/phone-agent.git .
```

**Option B: Direct Upload**
```bash
# From your local machine
rsync -avz --exclude 'venv' --exclude '*.pyc' --exclude '__pycache__' \
  ~/Desktop/IT-Friends/solutions/phone-agent/ \
  root@your-contabo-ip:/opt/phone-agent/
```

### Step 3: Database Setup (PostgreSQL for Production)

```bash
# On VPS
sudo -u postgres psql

# Create database and user
CREATE DATABASE phone_agent;
CREATE USER phone_agent_user WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE phone_agent TO phone_agent_user;
\q
```

### Step 4: Configure Environment

```bash
# On VPS
cd /opt/phone-agent

# Create .env file
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://phone_agent_user:your_secure_password@localhost/phone_agent

# Server
ITF_ENVIRONMENT=production
ITF_LOG_LEVEL=INFO
ITF_DEVICE_ID=contabo-vps-1

# AI Models (optional - can use cloud APIs)
GROQ_API_KEY=your_groq_key_here
DEEPGRAM_API_KEY=your_deepgram_key_here

# Domain (update with your actual domain)
ITF_DOMAIN=handwerk.your-domain.com
EOF

# Secure the file
chmod 600 .env
chown www-data:www-data .env
```

### Step 5: Run Deployment Script

```bash
# On VPS
cd /opt/phone-agent
chmod +x deploy/deploy.sh

# Deploy!
sudo ./deploy/deploy.sh
```

**The script will**:
1. Create virtual environment
2. Install Python dependencies
3. Run database migrations
4. Install systemd service
5. Start the application

### Step 6: Configure Nginx

```bash
# On VPS
# Copy Nginx config
cp /opt/phone-agent/deploy/nginx/phone-agent.conf /etc/nginx/sites-available/phone-agent

# Update domain name in config
nano /etc/nginx/sites-available/phone-agent
# Change: server_name handwerk-demo.example.com;
# To:     server_name handwerk.your-domain.com;

# Enable site
ln -s /etc/nginx/sites-available/phone-agent /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default  # Remove default site

# Test config
nginx -t

# Restart Nginx
systemctl restart nginx
```

### Step 7: Setup SSL with Let's Encrypt

```bash
# On VPS
certbot --nginx -d handwerk.your-domain.com

# Follow prompts to configure HTTPS
# Certbot will automatically update Nginx config
```

### Step 8: Verify Deployment

```bash
# Check service status
systemctl status phone-agent

# Check logs
journalctl -u phone-agent -f

# Test API
curl http://localhost:8080/health

# Test from outside
curl https://handwerk.your-domain.com/health
```

### Step 9: Access New Features

Once deployed, access at:

**Web Chat**:
```
https://handwerk.your-domain.com/static/chat.html
```

**Admin Dashboard**:
```
https://handwerk.your-domain.com/static/admin.html
```

**API Documentation**:
```
https://handwerk.your-domain.com/docs
```

## 📊 New Features Overview

### 1. Web Chat (`/static/chat.html`)

**What it does**:
- Customer intake for Handwerk jobs
- German LLM responses (Llama 3.2)
- Auto-categorizes trade type (SHK, Elektro, etc.)
- Creates jobs in database

**Database tables used**:
- `contacts` - Customer information
- `jobs` - Service requests

**No special deployment needed** - Just works!

### 2. Admin Dashboard (`/static/admin.html`)

**What it does**:
- View all jobs in real-time
- Filter by status, urgency, trade
- Update job status with one click
- View statistics (total, open, completed, etc.)

**API endpoints** (all at `/api/v1/jobs`):
- `GET /jobs` - List jobs
- `GET /jobs/stats` - Statistics
- `PATCH /jobs/{id}/status` - Update status

**No special deployment needed** - Just works!

### 3. LLM Integration

**What it does**:
- Powers German chat responses
- Uses Llama 3.2 (1B) locally

**Deployment options**:

**Option A: Cloud LLM** (Recommended for Contabo)
```bash
# In .env
GROQ_API_KEY=your_key_here  # Use Groq cloud API (fast, free)
```

**Option B: Local LLM** (Only if you have GPU)
```bash
# Download models (700MB)
cd /opt/phone-agent
python scripts/download_models.py
```

**For Contabo VPS**: Use Option A (cloud API) - local LLM would be too slow.

## 🔐 Security Considerations for New Features

### Admin Dashboard Access

**Current Status**: ⚠️ **No authentication** - anyone with URL can access

**For Production, Add Basic Auth**:

```nginx
# In /etc/nginx/sites-available/phone-agent
location /static/admin.html {
    auth_basic "Admin Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    alias /opt/phone-agent/static/admin.html;
}
```

Create password:
```bash
# Install htpasswd
apt install apache2-utils

# Create password file
htpasswd -c /etc/nginx/.htpasswd admin
# Enter password when prompted

# Restart Nginx
systemctl restart nginx
```

### Database Backups

The new features store data in PostgreSQL. Set up automatic backups:

```bash
# Create backup script
cat > /opt/phone-agent/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/phone-agent/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
pg_dump -U phone_agent_user phone_agent | gzip > $BACKUP_DIR/phone_agent_$DATE.sql.gz
# Keep only last 7 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
EOF

chmod +x /opt/phone-agent/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /opt/phone-agent/backup.sh
```

## 🧪 Testing After Deployment

### 1. Test Web Chat

```bash
# Visit in browser
https://handwerk.your-domain.com/static/chat.html

# Send test message
"Meine Heizung ist ausgefallen!"

# Check database
sudo -u postgres psql phone_agent
SELECT job_number, trade_category, status FROM jobs ORDER BY created_at DESC LIMIT 5;
\q
```

### 2. Test Admin Dashboard

```bash
# Visit in browser
https://handwerk.your-domain.com/static/admin.html

# Should see:
✅ Statistics cards with counts
✅ Filter dropdowns
✅ Job cards with details
✅ Action buttons working
```

### 3. Test API

```bash
# Get job stats
curl https://handwerk.your-domain.com/api/v1/jobs/stats

# List jobs
curl https://handwerk.your-domain.com/api/v1/jobs?page_size=5

# Update job status
curl -X PATCH https://handwerk.your-domain.com/api/v1/jobs/{job_id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "scheduled"}'
```

## 📈 Monitoring New Features

Add to your monitoring:

```bash
# Check if jobs are being created
journalctl -u phone-agent | grep "Job created via chat"

# Check LLM usage
journalctl -u phone-agent | grep "LLM"

# Monitor API response times
tail -f /var/log/nginx/phone-agent.access.log | grep "/api/v1/jobs"
```

## 🔄 Updating After Deployment

To update the code after initial deployment:

```bash
# On VPS
cd /opt/phone-agent

# Pull latest code
git pull

# Restart service
sudo systemctl restart phone-agent

# Check status
sudo systemctl status phone-agent
```

## 📋 Pre-Deployment Checklist

Before deploying to Contabo, make sure you have:

- [ ] Contabo VPS IP address
- [ ] Domain name configured (DNS A record pointing to VPS IP)
- [ ] GROQ API key (for cloud LLM) or models downloaded
- [ ] Database password decided (secure!)
- [ ] SSL certificate plan (Let's Encrypt is free)
- [ ] Admin dashboard password decided
- [ ] Backup strategy planned

## 🆘 Troubleshooting

### Issue: "Job created but not appearing in admin"

**Solution**: Check database connection
```bash
journalctl -u phone-agent | grep -i "database"
# Make sure DATABASE_URL is correct in .env
```

### Issue: "Admin dashboard shows 0 jobs"

**Solution**: Create test job via chat first
```bash
# Or insert directly
sudo -u postgres psql phone_agent
INSERT INTO jobs (job_number, title, trade_category, urgency, status)
VALUES ('TEST-001', 'Test Job', 'shk', 'normal', 'requested');
```

### Issue: "LLM not responding in chat"

**Solution**: Check if GROQ_API_KEY is set
```bash
# Check env
cat /opt/phone-agent/.env | grep GROQ

# Check logs
journalctl -u phone-agent | grep "LLM"
```

### Issue: "Nginx 404 for static files"

**Solution**: Check static file path in nginx config
```bash
# Should match location of static/ directory
ls -la /opt/phone-agent/static/
```

## ✅ Success Criteria

Deployment is successful when:

1. ✅ Health check returns 200: `curl https://your-domain.com/health`
2. ✅ Web chat loads and responds
3. ✅ Admin dashboard shows stats
4. ✅ Jobs can be created via chat
5. ✅ Job status can be updated in admin
6. ✅ HTTPS works with valid certificate
7. ✅ Service auto-starts on reboot

## 🎉 Next Steps After Deployment

Once deployed:

1. **Test thoroughly** - Create jobs, update statuses
2. **Set up monitoring** - Use existing monitoring stack
3. **Configure backups** - Daily database backups
4. **Add authentication** - Secure admin dashboard
5. **Monitor logs** - Watch for errors
6. **Scale if needed** - Add more Raspberry Pis to fleet

---

**Questions?** Check the main deployment docs:
- `docs/DEPLOYMENT.md` - Full deployment guide
- `docs/DEPLOYMENT_RPI5.md` - Raspberry Pi specific

**Ready to deploy!** 🚀

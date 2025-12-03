# Phone Agent - Raspberry Pi 5 Deployment Guide

Complete guide for deploying the IT-Friends Phone Agent on Raspberry Pi 5 for production use.

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Model | Raspberry Pi 5 4GB | Raspberry Pi 5 8GB |
| Storage | 32GB microSD (Class 10) | 64GB microSD (A2 rated) |
| Power Supply | Official 27W USB-C | Official 27W USB-C |
| Audio | USB audio adapter | USB audio adapter with speaker/mic |
| Network | Ethernet or WiFi | Ethernet (lower latency) |
| Cooling | Passive heatsink | Active cooler |

## Part 1: Operating System Setup

### 1.1 Flash Raspberry Pi OS

Use **Raspberry Pi Imager** to flash:
- **OS**: Raspberry Pi OS Lite (64-bit) - Bookworm
- **Hostname**: `itf-phone-agent` (or your preference)
- **SSH**: Enable with password authentication
- **WiFi**: Configure if not using Ethernet
- **Locale**: Set timezone and keyboard layout

### 1.2 Initial System Setup

After first boot, SSH into the Pi:

```bash
ssh pi@itf-phone-agent.local
# or use IP address: ssh pi@192.168.x.x
```

Update the system:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget
```

### 1.3 Configure Swap (Recommended for 4GB models)

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## Part 2: Install Dependencies

### 2.1 Python 3.11

Raspberry Pi OS Bookworm includes Python 3.11:

```bash
python3 --version  # Should show 3.11.x
sudo apt install -y python3-pip python3-venv
```

### 2.2 Audio Libraries

```bash
sudo apt install -y \
    libportaudio2 \
    libasound2 \
    libasound2-plugins \
    libespeak-ng1 \
    espeak-ng \
    alsa-utils
```

### 2.3 Additional System Dependencies

```bash
sudo apt install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    libopus-dev \
    libsndfile1
```

## Part 3: Application Installation

### 3.1 Create Application Directory

```bash
sudo mkdir -p /opt/itf
sudo chown pi:pi /opt/itf
cd /opt/itf
```

### 3.2 Clone Repository

```bash
git clone https://github.com/YOUR_ORG/IT-Friends.git
cd IT-Friends/solutions/phone-agent
```

### 3.3 Create Virtual Environment

```bash
python3 -m venv /opt/itf/venv
source /opt/itf/venv/bin/activate
```

### 3.4 Install Shared Library

```bash
cd /opt/itf/IT-Friends/solutions/shared-libs
pip install -e .
```

### 3.5 Install Phone Agent

```bash
cd /opt/itf/IT-Friends/solutions/phone-agent
pip install -e ".[production]"
```

### 3.6 Download AI Models

This downloads ~1.5GB of model files:

```bash
python scripts/download_models.py
```

**Note**: This may take 15-30 minutes on slower connections.

## Part 4: Configuration

### 4.1 Create Production Config

```bash
mkdir -p /opt/itf/config
cp configs/production.yaml /opt/itf/config/config.yaml
```

Edit the configuration:

```bash
nano /opt/itf/config/config.yaml
```

Key settings to configure:

```yaml
server:
  host: "0.0.0.0"
  port: 8080

industry:
  active: "gesundheit"  # or "handwerk"

telephony:
  sip_server: "your-sip-server.example.com"
  extension: "100"

logging:
  level: "INFO"
  file: "/var/log/itf/phone-agent.log"
```

### 4.2 Environment Variables

Create environment file:

```bash
sudo nano /opt/itf/.env
```

Add:

```bash
ITF_ENV=production
ITF_CONFIG_PATH=/opt/itf/config/config.yaml
ITF_LOG_LEVEL=INFO
ITF_DEVICE_ID=rpi5-001
```

### 4.3 Create Log Directory

```bash
sudo mkdir -p /var/log/itf
sudo chown pi:pi /var/log/itf
```

## Part 5: Systemd Service

### 5.1 Create Service File

```bash
sudo nano /etc/systemd/system/itf-phone-agent.service
```

Add:

```ini
[Unit]
Description=IT-Friends Phone Agent
After=network.target sound.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/opt/itf/IT-Friends/solutions/phone-agent
EnvironmentFile=/opt/itf/.env
ExecStart=/opt/itf/venv/bin/python -m phone_agent.main
Restart=always
RestartSec=10
StandardOutput=append:/var/log/itf/phone-agent.log
StandardError=append:/var/log/itf/phone-agent.log

# Resource limits
MemoryMax=3G
CPUQuota=90%

[Install]
WantedBy=multi-user.target
```

### 5.2 Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable itf-phone-agent
sudo systemctl start itf-phone-agent
```

### 5.3 Check Status

```bash
sudo systemctl status itf-phone-agent
```

### 5.4 View Logs

```bash
# Recent logs
journalctl -u itf-phone-agent -n 50

# Follow logs
journalctl -u itf-phone-agent -f

# Application log file
tail -f /var/log/itf/phone-agent.log
```

## Part 6: Verification

### 6.1 Health Check

From the Pi:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "device_id": "rpi5-001"
}
```

From another machine on the network:

```bash
curl http://itf-phone-agent.local:8080/health
```

### 6.2 Test Call Simulation

```bash
curl -X POST http://localhost:8080/api/v1/calls/test \
  -H "Content-Type: application/json" \
  -d '{"industry": "gesundheit", "scenario": "appointment"}'
```

### 6.3 Performance Check

Expected metrics on Pi 5 8GB:

| Metric | Expected Value |
|--------|----------------|
| API Response Time | < 100ms |
| Memory Usage | 1-2GB |
| CPU Usage (Idle) | < 10% |
| CPU Usage (Call) | 30-60% |

## Part 7: Audio Setup

### 7.1 List Audio Devices

```bash
aplay -l  # Output devices
arecord -l  # Input devices
```

### 7.2 Test Audio

```bash
# Test speaker
speaker-test -t wav -c 2

# Test microphone (5 second recording)
arecord -d 5 -f cd test.wav
aplay test.wav
```

### 7.3 Configure Default Audio

Edit ALSA config if needed:

```bash
sudo nano /etc/asound.conf
```

Example USB audio adapter config:

```
pcm.!default {
    type hw
    card 1
}

ctl.!default {
    type hw
    card 1
}
```

## Troubleshooting

### Service Won't Start

1. Check service status:
   ```bash
   sudo systemctl status itf-phone-agent -l
   ```

2. Check for Python errors:
   ```bash
   /opt/itf/venv/bin/python -c "import phone_agent"
   ```

3. Verify environment:
   ```bash
   source /opt/itf/venv/bin/activate
   echo $ITF_CONFIG_PATH
   ```

### Out of Memory

1. Check memory usage:
   ```bash
   free -h
   htop
   ```

2. Increase swap (see Part 1.3)

3. Reduce model size in config:
   ```yaml
   speech:
     model_size: "tiny"  # Instead of "base" or "small"
   ```

### Audio Issues

1. Check ALSA devices:
   ```bash
   aplay -L
   ```

2. Check permissions:
   ```bash
   groups pi  # Should include "audio"
   ```

3. Test with speaker-test:
   ```bash
   speaker-test -D hw:1,0 -t wav
   ```

### Network/SIP Issues

1. Check network:
   ```bash
   ping -c 3 your-sip-server.com
   ```

2. Check firewall:
   ```bash
   sudo ufw status
   ```

3. Test SIP connectivity (if using FreeSWITCH):
   ```bash
   nc -zv your-sip-server.com 5060
   ```

## Maintenance

### Update Application

```bash
cd /opt/itf/IT-Friends
git pull
source /opt/itf/venv/bin/activate
pip install -e solutions/phone-agent
sudo systemctl restart itf-phone-agent
```

### Log Rotation

Create logrotate config:

```bash
sudo nano /etc/logrotate.d/itf-phone-agent
```

Add:

```
/var/log/itf/*.log {
    daily
    missingok
    rotate 7
    compress
    notifempty
    create 0640 pi pi
}
```

### Backup Configuration

```bash
tar -czf itf-backup-$(date +%Y%m%d).tar.gz /opt/itf/config
```

## Security Recommendations

1. **Change default password**
   ```bash
   passwd pi
   ```

2. **Enable firewall**
   ```bash
   sudo apt install ufw
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow ssh
   sudo ufw allow 8080/tcp
   sudo ufw enable
   ```

3. **Use SSH keys instead of passwords**
   ```bash
   ssh-copy-id pi@itf-phone-agent.local
   ```

4. **Regular updates**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

## Support

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Check docs/ folder for more guides
- **Logs**: Include logs when reporting issues

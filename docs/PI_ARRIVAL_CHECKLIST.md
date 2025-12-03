# Raspberry Pi 5 Arrival Checklist

Step-by-step guide for setting up your Phone Agent when your Pi 5 arrives.

## Prerequisites (Prepare Before Pi Arrives)

### Hardware Checklist

- [ ] Raspberry Pi 5 (8GB recommended)
- [ ] Official Raspberry Pi 27W USB-C Power Supply
- [ ] Active Cooler or heatsink + fan
- [ ] 64GB+ A2 MicroSD card (or NVMe SSD with adapter)
- [ ] USB audio interface (for telephony) OR USB headset (for testing)
- [ ] Ethernet cable (recommended) or WiFi credentials

### Software Preparation (Do Now!)

- [ ] Download Raspberry Pi Imager: https://www.raspberrypi.com/software/
- [ ] Download Raspberry Pi OS Lite (64-bit, Bookworm): Pre-load in Imager
- [ ] Clone the Phone Agent repo to your development machine
- [ ] Download AI models (they're large, takes time):
  ```bash
  cd phone-agent
  pip install -e .
  python scripts/download_models.py
  ```

---

## Day 1: Hardware Setup (30 minutes)

### Step 1: Flash SD Card

1. Insert MicroSD card into your computer
2. Open Raspberry Pi Imager
3. Select:
   - **Device**: Raspberry Pi 5
   - **OS**: Raspberry Pi OS Lite (64-bit)
   - **Storage**: Your SD card
4. Click ⚙️ (Settings) and configure:
   ```
   Hostname: itf-phone-agent
   Enable SSH: Yes (password authentication)
   Username: itf
   Password: <your secure password>
   WiFi: <if needed>
   Locale: Europe/Berlin, de keyboard
   ```
5. Click **Write** and wait (~5 minutes)

### Step 2: First Boot

1. Insert SD card into Pi 5
2. Connect:
   - Ethernet cable (recommended)
   - Power supply (27W USB-C)
   - DO NOT connect display (headless setup)
3. Wait 2-3 minutes for first boot
4. Find Pi's IP address:
   ```bash
   # On your computer (macOS/Linux)
   ping itf-phone-agent.local

   # Or check your router's DHCP leases
   # Or use: nmap -sn 192.168.1.0/24
   ```

### Step 3: SSH Access

```bash
ssh itf@itf-phone-agent.local
# Enter your password
```

### Step 4: Initial System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Set timezone
sudo timedatectl set-timezone Europe/Berlin

# Enable I2C and SPI (for future accelerators)
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

# Configure swap (important for AI models)
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Reboot to apply changes
sudo reboot
```

---

## Day 1: Software Installation (1-2 hours)

### Step 5: Install Dependencies

```bash
# Reconnect after reboot
ssh itf@itf-phone-agent.local

# Install system dependencies
sudo apt install -y \
    python3-pip \
    python3-venv \
    git \
    curl \
    ffmpeg \
    libportaudio2 \
    libasound2-dev \
    libespeak-ng1 \
    sqlite3

# Install Docker (optional, for containerized deployment)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker itf
```

### Step 6: Create Application Directory

```bash
# Create directory structure
sudo mkdir -p /opt/itf/phone-agent
sudo chown -R itf:itf /opt/itf

# Create Python virtual environment
python3 -m venv /opt/itf/venv
source /opt/itf/venv/bin/activate

# Verify Python version (should be 3.11+)
python --version
```

### Step 7: Clone and Install Phone Agent

```bash
# Clone repository
cd /opt/itf
git clone https://github.com/IT-Friends/phone-agent.git
cd phone-agent

# Install shared libraries first
cd ../
git clone https://github.com/IT-Friends/shared-libs.git
cd shared-libs
pip install -e .
cd ../phone-agent

# Install phone-agent
pip install -e ".[dev]"
```

### Step 8: Transfer AI Models

From your development machine (where you pre-downloaded models):

```bash
# Create models directory on Pi
ssh itf@itf-phone-agent.local "mkdir -p /opt/itf/phone-agent/models/{whisper,llm,tts}"

# Transfer models (this takes a while)
scp -r models/whisper/* itf@itf-phone-agent.local:/opt/itf/phone-agent/models/whisper/
scp -r models/llm/* itf@itf-phone-agent.local:/opt/itf/phone-agent/models/llm/
scp -r models/tts/* itf@itf-phone-agent.local:/opt/itf/phone-agent/models/tts/
```

Or download directly on Pi (slower but works):

```bash
# On Pi
cd /opt/itf/phone-agent
source /opt/itf/venv/bin/activate
python scripts/download_models.py
```

---

## Day 1: Configuration & Testing (1 hour)

### Step 9: Configure Environment

```bash
cd /opt/itf/phone-agent

# Copy and edit environment file
cp .env.example .env
nano .env
```

Minimum configuration:
```bash
ITF_ENV=production
ITF_LOG_LEVEL=INFO
ITF_LOG_JSON=true
ITF_DEVICE_ID=  # Leave empty for auto-generation

# Database
ITF_DATABASE__URL=sqlite+aiosqlite:///data/phone_agent.db

# For testing without telephony
ITF_TELEPHONY__TWILIO__ENABLED=false
```

### Step 10: Initialize Database

```bash
source /opt/itf/venv/bin/activate
cd /opt/itf/phone-agent

# Create data directory
mkdir -p data

# Run database migrations
alembic upgrade head
```

### Step 11: Run Tests

```bash
# Run test suite
pytest tests/ -v

# Expected: 352+ tests passing
# Some tests may be skipped if telephony not configured
```

### Step 12: Start Application (Manual Test)

```bash
# Start the server
uvicorn phone_agent.main:app --host 0.0.0.0 --port 8080

# In another terminal (or from your computer)
curl http://itf-phone-agent.local:8080/health
```

Expected response:
```json
{"status": "healthy", "version": "0.1.0", ...}
```

---

## Day 2: Production Setup

### Step 13: Create Systemd Service

```bash
sudo nano /etc/systemd/system/phone-agent.service
```

Content:
```ini
[Unit]
Description=IT-Friends Phone Agent
After=network.target

[Service]
Type=simple
User=itf
Group=itf
WorkingDirectory=/opt/itf/phone-agent
Environment="PATH=/opt/itf/venv/bin"
EnvironmentFile=/opt/itf/phone-agent/.env
ExecStart=/opt/itf/venv/bin/uvicorn phone_agent.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

# Resource limits
MemoryMax=4G
CPUQuota=300%

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable phone-agent
sudo systemctl start phone-agent

# Check status
sudo systemctl status phone-agent

# View logs
sudo journalctl -u phone-agent -f
```

### Step 14: Audio Testing

```bash
# List audio devices
aplay -l
arecord -l

# Test speakers (if connected)
speaker-test -t wav -c 2

# Test microphone (record 5 seconds)
arecord -d 5 -f cd test.wav
aplay test.wav
```

### Step 15: AI Model Test

```bash
source /opt/itf/venv/bin/activate
cd /opt/itf/phone-agent

# Test STT (should print transcription)
python -c "
from phone_agent.ai.stt import get_stt
stt = get_stt()
stt.load()
print('STT loaded successfully')
"

# Test LLM
python -c "
from phone_agent.ai.llm import get_llm
llm = get_llm()
llm.load()
response = llm.generate('Sage Hallo auf Deutsch')
print(f'LLM response: {response}')
"

# Test TTS
python -c "
from phone_agent.ai.tts import get_tts
tts = get_tts()
tts.load()
audio = tts.synthesize('Hallo, ich bin der Phone Agent')
print(f'TTS generated {len(audio)} bytes')
"
```

---

## Verification Checklist

### System Health
- [ ] `curl http://localhost:8080/health` returns healthy
- [ ] `sudo systemctl status phone-agent` shows active (running)
- [ ] Memory usage under 4GB (`free -h`)
- [ ] CPU temperature under 70°C (`vcgencmd measure_temp`)

### AI Models
- [ ] STT model loads without errors
- [ ] LLM generates German text
- [ ] TTS produces audio output

### Audio (if configured)
- [ ] Microphone input works (`arecord`)
- [ ] Speaker output works (`aplay`)

### Database
- [ ] Database file exists in `data/`
- [ ] Migrations applied (`alembic current`)

### Tests
- [ ] All 352+ tests pass
- [ ] No import errors

---

## Performance Benchmarks

Run after setup to verify performance:

```bash
# Benchmark script
python -c "
import time
from phone_agent.ai.stt import get_stt
from phone_agent.ai.llm import get_llm
from phone_agent.ai.tts import get_tts

print('Loading models...')

# STT
start = time.time()
stt = get_stt()
stt.load()
print(f'STT load time: {time.time() - start:.2f}s')

# LLM
start = time.time()
llm = get_llm()
llm.load()
print(f'LLM load time: {time.time() - start:.2f}s')

# TTS
start = time.time()
tts = get_tts()
tts.load()
print(f'TTS load time: {time.time() - start:.2f}s')

# Inference benchmarks
print()
print('Running inference benchmarks...')

# LLM inference
start = time.time()
response = llm.generate('Wie kann ich Ihnen helfen?')
print(f'LLM inference: {time.time() - start:.2f}s')

# TTS synthesis
start = time.time()
audio = tts.synthesize('Guten Tag, hier ist die Praxis.')
print(f'TTS synthesis: {time.time() - start:.2f}s')

print()
print('Expected targets:')
print('- STT: <500ms')
print('- LLM: <1000ms')
print('- TTS: <300ms')
"
```

Target benchmarks (Raspberry Pi 5, no accelerator):
| Component | Target | Typical |
|-----------|--------|---------|
| STT Latency | <500ms | ~400ms |
| LLM Inference | <1000ms | ~800ms |
| TTS Synthesis | <300ms | ~250ms |
| End-to-End | <2000ms | ~1500ms |
| Memory Total | <4GB | ~2.8GB |

---

## Troubleshooting

### Pi won't boot
- Check power supply is 27W USB-C
- Re-flash SD card
- Try different SD card

### Can't find Pi on network
```bash
# Scan local network
nmap -sn 192.168.1.0/24 | grep -i raspberry
```

### Out of memory
```bash
# Increase swap
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=4096/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### Service won't start
```bash
# Check logs
sudo journalctl -u phone-agent -n 100

# Common issues:
# - Missing .env file
# - Database not initialized
# - Model files missing
```

### AI models load slowly
- First load is always slower (cold cache)
- Subsequent loads are faster
- Consider enabling model preloading in config

---

## Next Steps After Setup

1. **Configure Telephony** - Set up Twilio or sipgate credentials
2. **Test Call Flow** - Use web audio interface for testing
3. **Connect Calendar** - Configure Google Calendar integration
4. **Enable SMS/Email** - Set up notification integrations
5. **Remote Access** - Set up Tailscale for secure remote management

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full production setup.

---

*Welcome to IT-Friends Phone Agent! 🎉*

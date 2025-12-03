#!/bin/bash
# FreeSWITCH Setup Script for Raspberry Pi 5
#
# Installs and configures FreeSWITCH for the Phone Agent.
# This script should be run with sudo.
#
# Usage:
#   sudo ./setup_freeswitch.sh

set -e

echo "============================================"
echo "  IT-Friends Phone Agent - FreeSWITCH Setup"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Configuration
PHONE_AGENT_HOST="127.0.0.1"
PHONE_AGENT_PORT="9090"

# Security: ESL password must be provided via environment variable
if [ -z "$ESL_PASSWORD" ]; then
    echo "ERROR: ESL_PASSWORD environment variable is not set."
    echo "Please set it before running this script:"
    echo "  export ESL_PASSWORD='your-secure-password'"
    echo ""
    echo "Generate a secure password with:"
    echo "  openssl rand -base64 32"
    exit 1
fi

echo "[1/6] Installing dependencies..."
apt-get update
apt-get install -y \
    gnupg2 \
    wget \
    lsb-release \
    ca-certificates

echo "[2/6] Adding FreeSWITCH repository..."
# Add SignalWire repository (FreeSWITCH maintainer)
TOKEN="pat_YOUR_SIGNALWIRE_TOKEN"  # Get free token from signalwire.com

if [ "$TOKEN" = "pat_YOUR_SIGNALWIRE_TOKEN" ]; then
    echo ""
    echo "WARNING: Using default SignalWire token."
    echo "For production, get a free token from https://signalwire.com"
    echo "and update this script."
    echo ""
fi

# Alternative: Install from Debian packages (simpler for Pi)
echo "Installing FreeSWITCH from Debian packages..."
apt-get install -y \
    freeswitch \
    freeswitch-mod-commands \
    freeswitch-mod-console \
    freeswitch-mod-dialplan-xml \
    freeswitch-mod-dptools \
    freeswitch-mod-event-socket \
    freeswitch-mod-logfile \
    freeswitch-mod-sndfile \
    freeswitch-mod-sofia \
    freeswitch-mod-tone-stream \
    freeswitch-sounds-en-us-callie

# If packages not available, build from source
if ! command -v freeswitch &> /dev/null; then
    echo "FreeSWITCH packages not available, installing via snap..."
    snap install freeswitch
fi

echo "[3/6] Configuring Event Socket..."
# Create ESL configuration
cat > /etc/freeswitch/autoload_configs/event_socket.conf.xml << EOF
<configuration name="event_socket.conf" description="Socket Client">
  <settings>
    <param name="nat-map" value="false"/>
    <param name="listen-ip" value="127.0.0.1"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="${ESL_PASSWORD}"/>
    <param name="apply-inbound-acl" value="loopback.auto"/>
  </settings>
</configuration>
EOF

echo "[4/6] Creating Phone Agent dialplan..."
# Create dialplan for Phone Agent
cat > /etc/freeswitch/dialplan/default/00_phone_agent.xml << EOF
<include>
  <!-- Phone Agent Inbound Handler -->
  <extension name="phone_agent_inbound">
    <condition field="destination_number" expression="^(\d{10,})$">
      <action application="answer"/>
      <action application="sleep" data="500"/>
      <!-- Connect to Phone Agent audio bridge -->
      <action application="socket" data="${PHONE_AGENT_HOST}:${PHONE_AGENT_PORT} async full"/>
    </condition>
  </extension>

  <!-- Emergency Transfer -->
  <extension name="emergency_transfer">
    <condition field="destination_number" expression="^112$">
      <action application="transfer" data="112 XML emergency"/>
    </condition>
  </extension>

  <!-- Internal Extension for Testing -->
  <extension name="phone_agent_test">
    <condition field="destination_number" expression="^9999$">
      <action application="answer"/>
      <action application="playback" data="ivr/ivr-welcome.wav"/>
      <action application="socket" data="${PHONE_AGENT_HOST}:${PHONE_AGENT_PORT} async full"/>
    </condition>
  </extension>
</include>
EOF

echo "[5/6] Configuring SIP profile..."
# Update internal SIP profile for local network
cat > /etc/freeswitch/sip_profiles/internal.xml << EOF
<profile name="internal">
  <settings>
    <param name="debug" value="0"/>
    <param name="sip-trace" value="no"/>
    <param name="rtp-ip" value="\$\${local_ip_v4}"/>
    <param name="sip-ip" value="\$\${local_ip_v4}"/>
    <param name="ext-rtp-ip" value="auto-nat"/>
    <param name="ext-sip-ip" value="auto-nat"/>
    <param name="sip-port" value="5060"/>
    <param name="nonce-ttl" value="60"/>
    <param name="context" value="default"/>
    <param name="inbound-codec-prefs" value="PCMU,PCMA"/>
    <param name="outbound-codec-prefs" value="PCMU,PCMA"/>
    <param name="rtp-timeout-sec" value="300"/>
    <param name="rtp-hold-timeout-sec" value="1800"/>
  </settings>
</profile>
EOF

echo "[6/6] Starting FreeSWITCH..."
systemctl enable freeswitch
systemctl restart freeswitch

# Wait for FreeSWITCH to start
sleep 5

# Test ESL connection
echo ""
echo "Testing ESL connection..."
if command -v fs_cli &> /dev/null; then
    fs_cli -x "status" || echo "Note: fs_cli test failed, but service may still be running"
fi

echo ""
echo "============================================"
echo "  FreeSWITCH Setup Complete!"
echo "============================================"
echo ""
echo "Configuration:"
echo "  ESL Host: 127.0.0.1"
echo "  ESL Port: 8021"
echo "  ESL Password: ********** (from ESL_PASSWORD env var)"
echo ""
echo "Phone Agent Audio Bridge:"
echo "  Host: ${PHONE_AGENT_HOST}"
echo "  Port: ${PHONE_AGENT_PORT}"
echo ""
echo "Test extension: Dial 9999 to test Phone Agent"
echo ""
echo "Update your phone_agent config:"
echo "  telephony:"
echo "    enabled: true"
echo "    backend: freeswitch"
echo "    freeswitch:"
echo "      host: 127.0.0.1"
echo "      port: 8021"
echo "      password: \${ESL_PASSWORD}  # Set via environment variable"
echo ""

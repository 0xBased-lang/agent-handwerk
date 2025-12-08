#!/bin/bash
# IT-Friends Phone Agent - VPS Deployment Script
# Usage: ./deploy.sh [contabo|local]

set -e

# Configuration
DEPLOY_DIR="/opt/phone-agent"
SERVICE_NAME="phone-agent"
USER="www-data"
GROUP="www-data"
PYTHON_VERSION="3.11"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; exit 1; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root (sudo ./deploy.sh)"
fi

log "Starting IT-Friends Phone Agent deployment..."

# Create directories
log "Creating directories..."
mkdir -p ${DEPLOY_DIR}/{data,logs,static}
chown -R ${USER}:${GROUP} ${DEPLOY_DIR}

# Check for .env file
if [ ! -f "${DEPLOY_DIR}/.env" ]; then
    if [ -f "${DEPLOY_DIR}/.env.template" ]; then
        warn ".env file not found. Please copy .env.template to .env and configure it."
        cp ${DEPLOY_DIR}/.env.template ${DEPLOY_DIR}/.env.example
    else
        warn ".env file not found. Please create one based on the template."
    fi
fi

# Create virtual environment
log "Setting up Python virtual environment..."
if [ ! -d "${DEPLOY_DIR}/venv" ]; then
    python${PYTHON_VERSION} -m venv ${DEPLOY_DIR}/venv
fi

# Install dependencies
log "Installing dependencies..."
${DEPLOY_DIR}/venv/bin/pip install --upgrade pip
${DEPLOY_DIR}/venv/bin/pip install -e "${DEPLOY_DIR}[dev]"

# Run database migrations
log "Running database migrations..."
cd ${DEPLOY_DIR}
${DEPLOY_DIR}/venv/bin/alembic upgrade head

# Install systemd service
log "Installing systemd service..."
cp ${DEPLOY_DIR}/deploy/systemd/phone-agent.service /etc/systemd/system/
systemctl daemon-reload

# Enable and start service
log "Enabling and starting service..."
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

# Wait for service to start
sleep 3

# Check status
if systemctl is-active --quiet ${SERVICE_NAME}; then
    log "Service started successfully!"
    log ""
    log "=== Deployment Complete ==="
    log ""
    log "Service status: $(systemctl is-active ${SERVICE_NAME})"
    log "Access the demo at: http://$(hostname -I | awk '{print $1}'):8080/demo/handwerk"
    log ""
    log "Useful commands:"
    log "  sudo systemctl status ${SERVICE_NAME}    # Check status"
    log "  sudo journalctl -u ${SERVICE_NAME} -f    # View logs"
    log "  sudo systemctl restart ${SERVICE_NAME}   # Restart service"
    log ""
else
    error "Service failed to start. Check logs with: journalctl -u ${SERVICE_NAME}"
fi

#!/bin/bash
# IT-Friends Handwerk - VPS Deployment
# =====================================
# Deploys Handwerk Phone Agent + Dashboard to VPS
# Runs alongside Lieferservice on separate ports (8180, 3100)
#
# Usage:
#   ./deploy/deploy-full-stack.sh contabo           # Deploy to contabo VPS
#   ./deploy/deploy-full-stack.sh contabo --build   # Force rebuild
#   ./deploy/deploy-full-stack.sh contabo --logs    # Show logs after deploy

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REMOTE_DIR="/opt/handwerk"
COMPOSE_FILE="docker-compose.vps.yml"
NETWORK_NAME="handwerk-network"

# Ports (different from Lieferservice)
API_PORT=8180
DASHBOARD_PORT=3100

# Parse arguments
VPS_HOST="${1:-}"
FORCE_BUILD=false
SHOW_LOGS=false

shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            FORCE_BUILD=true
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

if [[ -z "$VPS_HOST" ]]; then
    echo -e "${RED}Usage: $0 <vps-host> [--build] [--logs]${NC}"
    echo ""
    echo "Arguments:"
    echo "  vps-host    SSH alias or hostname (e.g., contabo)"
    echo "  --build     Force Docker image rebuild"
    echo "  --logs      Show container logs after deployment"
    echo ""
    echo "Ports:"
    echo "  API:        $API_PORT (Phone Agent)"
    echo "  Dashboard:  $DASHBOARD_PORT (Next.js)"
    exit 1
fi

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}IT-Friends Handwerk - VPS Deployment${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""
echo -e "VPS Host:     ${GREEN}$VPS_HOST${NC}"
echo -e "Remote Dir:   ${GREEN}$REMOTE_DIR${NC}"
echo -e "API Port:     ${GREEN}$API_PORT${NC}"
echo -e "Dashboard:    ${GREEN}$DASHBOARD_PORT${NC}"
echo -e "Force Build:  ${GREEN}$FORCE_BUILD${NC}"
echo ""

# Step 1: Verify SSH connection
echo -e "${YELLOW}[1/8] Verifying SSH connection...${NC}"
if ! ssh -o ConnectTimeout=5 "$VPS_HOST" "echo 'Connected'" > /dev/null 2>&1; then
    echo -e "${RED}Failed to connect to $VPS_HOST${NC}"
    exit 1
fi
echo -e "${GREEN}SSH connection successful${NC}"

# Step 2: Rename old directory if exists
echo -e "${YELLOW}[2/8] Setting up remote directory...${NC}"
ssh "$VPS_HOST" "sudo mv /opt/phone-agent $REMOTE_DIR 2>/dev/null || true"
ssh "$VPS_HOST" "sudo mkdir -p $REMOTE_DIR/{data/handwerk,models,static,configs,prompts,dashboard}"
ssh "$VPS_HOST" "sudo chown -R \$(whoami):\$(whoami) $REMOTE_DIR"
# Fix permissions for container user (uid 1000)
ssh "$VPS_HOST" "sudo chown -R 1000:1000 $REMOTE_DIR/data/handwerk"

# Step 3: Sync project files
echo -e "${YELLOW}[3/8] Syncing project files...${NC}"
rsync -avz --progress \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache' \
    --exclude '.mypy_cache' \
    --exclude '.ruff_cache' \
    --exclude 'node_modules' \
    --exclude '.next' \
    --exclude 'data/' \
    --exclude 'models/*.bin' \
    --exclude 'models/*.onnx' \
    --exclude '*.egg-info' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude '.env' \
    --exclude '.env.local' \
    "$PROJECT_DIR/" "$VPS_HOST:$REMOTE_DIR/"

# Step 4: Copy environment file if exists
echo -e "${YELLOW}[4/8] Setting up environment...${NC}"
if [[ -f "$PROJECT_DIR/.env" ]]; then
    scp "$PROJECT_DIR/.env" "$VPS_HOST:$REMOTE_DIR/.env"
    echo -e "${GREEN}Environment file copied${NC}"
elif [[ -f "$PROJECT_DIR/.env.vps" ]]; then
    scp "$PROJECT_DIR/.env.vps" "$VPS_HOST:$REMOTE_DIR/.env"
    echo -e "${GREEN}VPS environment file copied${NC}"
else
    # Check if .env exists on remote, if not create from example
    if ! ssh "$VPS_HOST" "test -f $REMOTE_DIR/.env"; then
        echo -e "${YELLOW}Creating .env from example...${NC}"
        ssh "$VPS_HOST" "cp $REMOTE_DIR/.env.vps.example $REMOTE_DIR/.env 2>/dev/null || cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env 2>/dev/null || true"
    fi
    echo -e "${YELLOW}Using existing .env on VPS${NC}"
fi

# Step 5: Create Docker network if not exists
echo -e "${YELLOW}[5/8] Setting up Docker network...${NC}"
ssh "$VPS_HOST" "docker network create $NETWORK_NAME 2>/dev/null || true"

# Step 6: Stop existing containers
echo -e "${YELLOW}[6/8] Stopping existing Handwerk containers...${NC}"
ssh "$VPS_HOST" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE down --remove-orphans 2>/dev/null || true"

# Step 7: Deploy with Docker Compose
echo -e "${YELLOW}[7/8] Deploying with Docker Compose...${NC}"
BUILD_ARG=""
if [[ "$FORCE_BUILD" == "true" ]]; then
    BUILD_ARG="--build"
    echo -e "${YELLOW}Clearing Docker build cache...${NC}"
    ssh "$VPS_HOST" "docker builder prune -f 2>/dev/null || true"
fi

ssh "$VPS_HOST" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE up -d $BUILD_ARG"

# Step 8: Wait for services to be healthy
echo -e "${YELLOW}[8/8] Waiting for services to be healthy...${NC}"
sleep 15

# Check health
MAX_RETRIES=30
RETRY_COUNT=0

while [[ $RETRY_COUNT -lt $MAX_RETRIES ]]; do
    # Check Phone Agent health
    PA_HEALTH=$(ssh "$VPS_HOST" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$API_PORT/health 2>/dev/null || echo '000'")

    # Check Dashboard health
    DASH_HEALTH=$(ssh "$VPS_HOST" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$DASHBOARD_PORT/ 2>/dev/null || echo '000'")

    if [[ "$PA_HEALTH" == "200" ]] && [[ "$DASH_HEALTH" == "200" ]]; then
        echo -e "${GREEN}All services healthy!${NC}"
        break
    fi

    echo -e "Waiting... (Phone Agent: $PA_HEALTH, Dashboard: $DASH_HEALTH)"
    sleep 5
    ((RETRY_COUNT++))
done

if [[ $RETRY_COUNT -eq $MAX_RETRIES ]]; then
    echo -e "${YELLOW}Warning: Services may not be fully healthy${NC}"
    echo -e "Phone Agent: $PA_HEALTH, Dashboard: $DASH_HEALTH"
fi

# Get VPS IP
VPS_IP=$(ssh "$VPS_HOST" "curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print \$1}'")

# Final status
echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}Handwerk Deployment Complete!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "Handwerk Services:"
echo -e "  Dashboard:     ${BLUE}http://$VPS_IP:$DASHBOARD_PORT/${NC}"
echo -e "  API:           ${BLUE}http://$VPS_IP:$API_PORT/api/${NC}"
echo -e "  API Docs:      ${BLUE}http://$VPS_IP:$API_PORT/docs${NC}"
echo -e "  Health:        ${BLUE}http://$VPS_IP:$API_PORT/health${NC}"
echo -e "  Legacy Admin:  ${BLUE}http://$VPS_IP:$API_PORT/static/admin.html${NC}"
echo ""
echo -e "Lieferservice (unchanged):"
echo -e "  App:           ${BLUE}http://$VPS_IP/${NC}"
echo -e "  API:           ${BLUE}http://$VPS_IP:8080/api/${NC}"
echo ""

# Show logs if requested
if [[ "$SHOW_LOGS" == "true" ]]; then
    echo -e "${YELLOW}Showing container logs (Ctrl+C to exit)...${NC}"
    ssh "$VPS_HOST" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE logs -f"
fi

# Show container status
echo -e "Container Status:"
ssh "$VPS_HOST" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE ps"

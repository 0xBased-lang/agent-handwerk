#!/bin/bash
# ==============================================================================
# IT-Friends Phone Agent - Handwerk Deployment Script
# ==============================================================================
#
# Deploys the Handwerk phone agent to a VPS server.
#
# Usage:
#   ./deploy-handwerk.sh [server-alias]
#
# Examples:
#   ./deploy-handwerk.sh contabo       # Deploy to contabo VPS
#   ./deploy-handwerk.sh               # Deploy to default server (contabo)
#
# Prerequisites:
#   - SSH access to VPS with key authentication
#   - Docker and docker-compose installed on VPS
#   - Groq API key configured in .env
#
# ==============================================================================

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_ALIAS="${1:-contabo}"
REMOTE_DIR="/opt/phone-agent-handwerk"
COMPOSE_FILE="docker-compose.handwerk.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ==============================================================================
# Pre-flight checks
# ==============================================================================

log_info "Starting Handwerk Phone Agent deployment to ${SERVER_ALIAS}..."

# Check if docker-compose.handwerk.yml exists
if [[ ! -f "$PROJECT_DIR/$COMPOSE_FILE" ]]; then
    log_error "Docker compose file not found: $PROJECT_DIR/$COMPOSE_FILE"
    exit 1
fi

# Check if .env exists (or .env.handwerk)
if [[ -f "$PROJECT_DIR/.env" ]]; then
    ENV_FILE=".env"
elif [[ -f "$PROJECT_DIR/.env.handwerk" ]]; then
    ENV_FILE=".env.handwerk"
else
    log_warning "No .env file found. Creating from example..."
    if [[ -f "$PROJECT_DIR/.env.handwerk.example" ]]; then
        cp "$PROJECT_DIR/.env.handwerk.example" "$PROJECT_DIR/.env"
        log_warning "Please configure .env with your settings before deploying!"
        exit 1
    else
        log_error "No .env or .env.handwerk.example found"
        exit 1
    fi
fi

# Check SSH connection
log_info "Testing SSH connection to $SERVER_ALIAS..."
if ! ssh -o ConnectTimeout=10 "$SERVER_ALIAS" "echo 'SSH OK'" &>/dev/null; then
    log_error "Cannot connect to $SERVER_ALIAS via SSH"
    log_info "Make sure you have SSH configured in ~/.ssh/config"
    exit 1
fi
log_success "SSH connection successful"

# ==============================================================================
# Create remote directory structure
# ==============================================================================

log_info "Creating remote directory structure..."
ssh "$SERVER_ALIAS" "sudo mkdir -p $REMOTE_DIR/{data,models,static,configs,prompts} && sudo chown -R \$USER:\$USER $REMOTE_DIR"
log_success "Remote directories created"

# ==============================================================================
# Sync files to VPS
# ==============================================================================

log_info "Syncing project files to VPS..."

# Sync core files
rsync -avz --progress \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.pytest_cache' \
    --exclude '.mypy_cache' \
    --exclude '.ruff_cache' \
    --exclude 'tests/' \
    --exclude 'docs/' \
    --exclude '*.egg-info' \
    --exclude '.venv' \
    --exclude 'data/*.db' \
    --exclude 'models/*.bin' \
    "$PROJECT_DIR/src/" "$SERVER_ALIAS:$REMOTE_DIR/src/"

# Sync static files
rsync -avz --progress \
    "$PROJECT_DIR/static/" "$SERVER_ALIAS:$REMOTE_DIR/static/"

# Sync config files
rsync -avz --progress \
    "$PROJECT_DIR/configs/" "$SERVER_ALIAS:$REMOTE_DIR/configs/"

# Sync prompts
if [[ -d "$PROJECT_DIR/prompts" ]]; then
    rsync -avz --progress \
        "$PROJECT_DIR/prompts/" "$SERVER_ALIAS:$REMOTE_DIR/prompts/"
fi

# Sync deployment files
rsync -avz --progress \
    "$PROJECT_DIR/$COMPOSE_FILE" \
    "$PROJECT_DIR/Dockerfile" \
    "$PROJECT_DIR/pyproject.toml" \
    "$PROJECT_DIR/requirements.txt" \
    "$PROJECT_DIR/$ENV_FILE" \
    "$SERVER_ALIAS:$REMOTE_DIR/"

# Rename env file to .env on remote
if [[ "$ENV_FILE" != ".env" ]]; then
    ssh "$SERVER_ALIAS" "mv $REMOTE_DIR/$ENV_FILE $REMOTE_DIR/.env"
fi

log_success "Files synced successfully"

# ==============================================================================
# Check for AI models
# ==============================================================================

log_info "Checking AI models on VPS..."
MODELS_EXIST=$(ssh "$SERVER_ALIAS" "ls $REMOTE_DIR/models/*.bin 2>/dev/null | wc -l" || echo "0")

if [[ "$MODELS_EXIST" -eq 0 ]]; then
    log_warning "No AI models found on VPS."
    log_info "You can either:"
    log_info "  1. Run with Groq Cloud (GROQ_API_KEY in .env) - recommended"
    log_info "  2. Download models manually: ssh $SERVER_ALIAS 'cd $REMOTE_DIR && python scripts/download_models.py'"
    log_info ""
    log_info "Continuing with Groq Cloud inference..."
fi

# ==============================================================================
# Build and deploy
# ==============================================================================

log_info "Building and deploying Docker container..."

ssh "$SERVER_ALIAS" << EOF
cd $REMOTE_DIR

# Pull latest base images
docker compose -f $COMPOSE_FILE pull || true

# Build and start
docker compose -f $COMPOSE_FILE build --no-cache
docker compose -f $COMPOSE_FILE up -d

# Wait for health check
echo "Waiting for service to be healthy..."
sleep 10

# Check health
for i in {1..30}; do
    if curl -sf http://localhost:8080/health > /dev/null; then
        echo "Service is healthy!"
        break
    fi
    echo "Waiting for service... (attempt \$i/30)"
    sleep 5
done

# Show status
docker compose -f $COMPOSE_FILE ps
EOF

# ==============================================================================
# Verify deployment
# ==============================================================================

log_info "Verifying deployment..."

# Get public IP or use Tailscale
VPS_IP=$(ssh "$SERVER_ALIAS" "curl -sf ifconfig.me || hostname -I | awk '{print \$1}'" 2>/dev/null)

# Test health endpoint
if ssh "$SERVER_ALIAS" "curl -sf http://localhost:8080/health" &>/dev/null; then
    log_success "Deployment successful!"
    echo ""
    echo "=============================================="
    echo -e "${GREEN}Handwerk Phone Agent is running!${NC}"
    echo "=============================================="
    echo ""
    echo "Access URLs:"
    echo "  - API:        http://${VPS_IP}:8080"
    echo "  - Health:     http://${VPS_IP}:8080/health"
    echo "  - API Docs:   http://${VPS_IP}:8080/docs"
    echo "  - Admin:      http://${VPS_IP}:8080/static/admin.html"
    echo "  - Chat:       http://${VPS_IP}:8080/static/chat.html"
    echo ""
    echo "Useful commands:"
    echo "  - View logs:   ssh $SERVER_ALIAS 'cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE logs -f'"
    echo "  - Restart:     ssh $SERVER_ALIAS 'cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE restart'"
    echo "  - Stop:        ssh $SERVER_ALIAS 'cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE down'"
    echo ""
else
    log_error "Deployment may have issues. Check logs with:"
    echo "  ssh $SERVER_ALIAS 'cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE logs'"
    exit 1
fi

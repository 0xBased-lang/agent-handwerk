#!/bin/bash
# IT-Friends Phone Agent - Docker Compose Deployment
# Usage: ./docker-deploy.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo "================================"
echo "IT-Friends Handwerk Demo Deploy"
echo "================================"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    error "Docker not installed. Run: curl -fsSL https://get.docker.com | sh"
fi
log "Docker found: $(docker --version | cut -d' ' -f3)"

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    error "Docker Compose not found. Install docker-compose-plugin"
fi
log "Docker Compose found"

# Change to project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
log "Working directory: $PROJECT_DIR"

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f "deploy/.env.template" ]; then
        warn ".env not found. Creating from template..."
        cp deploy/.env.template .env
        echo ""
        echo "=========================================="
        echo "IMPORTANT: Edit .env with your API keys:"
        echo "=========================================="
        echo "  nano .env"
        echo ""
        echo "Required keys:"
        echo "  - GROQ_API_KEY"
        echo "  - DEEPGRAM_API_KEY"
        echo "  - ELEVENLABS_API_KEY"
        echo ""
        echo "Then run this script again."
        exit 0
    else
        error ".env.template not found"
    fi
fi

# Validate required API keys and configuration
source .env 2>/dev/null || true
if [ -z "$GROQ_API_KEY" ] || [ "$GROQ_API_KEY" = "your_groq_api_key_here" ]; then
    warn "GROQ_API_KEY not configured in .env"
fi
if [ -z "$DEEPGRAM_API_KEY" ] || [ "$DEEPGRAM_API_KEY" = "your_deepgram_api_key_here" ]; then
    warn "DEEPGRAM_API_KEY not configured in .env"
fi
if [ -z "$ELEVENLABS_API_KEY" ] || [ "$ELEVENLABS_API_KEY" = "your_elevenlabs_api_key_here" ]; then
    warn "ELEVENLABS_API_KEY not configured in .env"
fi

# Validate JWT secret for multi-tenant auth (required in production)
if [ "$ITF_ENVIRONMENT" = "production" ]; then
    if [ -z "$ITF_JWT_SECRET_KEY" ] || [ "$ITF_JWT_SECRET_KEY" = "GENERATE_A_SECURE_KEY_HERE" ]; then
        warn "ITF_JWT_SECRET_KEY not configured for production!"
        warn "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    fi
fi

# Create data directory
mkdir -p data
log "Data directory ready"

# Build and deploy
echo ""
log "Building Docker image..."
docker compose -f docker-compose.prod.yml build phone-agent

echo ""
log "Starting services..."
docker compose -f docker-compose.prod.yml up -d phone-agent

# Wait for startup
echo ""
log "Waiting for service to start..."
sleep 5

# Health check
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    log "Health check passed!"
else
    warn "Health check pending (may still be starting)"
fi

# Show status
echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo ""
echo "Access the demo at:"
echo "  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'YOUR_IP'):8080/demo/handwerk"
echo ""
echo "Useful commands:"
echo "  docker compose -f docker-compose.prod.yml logs -f    # View logs"
echo "  docker compose -f docker-compose.prod.yml ps         # Check status"
echo "  docker compose -f docker-compose.prod.yml down       # Stop services"
echo ""

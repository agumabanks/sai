#!/bin/bash
set -e

VENV="/opt/antigravity/venv"
BACKEND="/var/www/ai.sanaa.co/backend"
FRONTEND="/var/www/ai.sanaa.co/frontend"

echo "=== Sanaa AI Mission Init ==="

# Install pytest and test dependencies in venv (idempotent)
echo "Installing Python test dependencies..."
$VENV/bin/pip install -q pytest pytest-asyncio pytest-cov 2>/dev/null || true

# Install missing backend dependencies
echo "Installing missing backend dependencies..."
$VENV/bin/pip install -q duckduckgo-search aiomysql beautifulsoup4 bcrypt cryptography 2>/dev/null || true

# Install backend requirements
echo "Installing backend requirements..."
$VENV/bin/pip install -q -r $BACKEND/requirements.txt 2>/dev/null || true

# Create backend test directory if it doesn't exist
mkdir -p $BACKEND/tests
touch $BACKEND/tests/__init__.py

# Install frontend dependencies (idempotent)
echo "Installing frontend dependencies..."
cd $FRONTEND && composer install --no-interaction --quiet 2>/dev/null || true

# Verify services are running
echo "Checking services..."
pg_isready -h localhost -p 5432 -q && echo "  PostgreSQL: OK" || echo "  PostgreSQL: NOT RUNNING"
redis-cli ping > /dev/null 2>&1 && echo "  Redis: OK" || echo "  Redis: NOT RUNNING"
curl -sf http://127.0.0.1:8101/api/health > /dev/null && echo "  Backend API: OK" || echo "  Backend API: NOT RUNNING"
curl -sf http://127.0.0.1:11434/api/tags > /dev/null && echo "  Ollama: OK" || echo "  Ollama: NOT RUNNING"

echo "=== Init Complete ==="

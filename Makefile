# Mike Logger - Development and Deployment Commands

.PHONY: help build up down logs shell test clean install

# Default target
help:
	@echo "Mike Logger - Available Commands:"
	@echo ""
	@echo "  make build     - Build all Docker images"
	@echo "  make up        - Start all services"
	@echo "  make down      - Stop all services"
	@echo "  make logs      - Show logs from all services"
	@echo "  make shell     - Open shell in processor container"
	@echo "  make test      - Run tests"
	@echo "  make clean     - Clean up containers and volumes"
	@echo "  make install   - Install host dependencies for audio capture"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make install    # Install Python deps for audio capture"
	@echo "  2. cp .env.example .env  # Configure environment"
	@echo "  3. make build      # Build Docker images"
	@echo "  4. make up         # Start services"
	@echo "  5. python3 host_audio_capture.py  # Start audio capture"

# Build all Docker images
build:
	@echo "🐳 Building Docker images..."
	docker-compose build

# Start all services
up:
	@echo "🚀 Starting Mike Logger services..."
	docker-compose up -d
	@echo "✅ Services started!"
	@echo "   Dashboard: http://localhost:8080"
	@echo "   Metrics: http://localhost:9090"
	@echo "   Start audio capture: python3 host_audio_capture.py"

# Start with rebuild
up-build:
	@echo "🚀 Building and starting Mike Logger services..."
	docker-compose up -d --build

# Stop all services
down:
	@echo "🛑 Stopping Mike Logger services..."
	docker-compose down

# Show logs
logs:
	docker-compose logs -f

# Show logs for specific service
logs-processor:
	docker-compose logs -f processor

logs-dashboard:
	docker-compose logs -f dashboard

# Open shell in processor container
shell:
	docker-compose exec processor bash

# Run tests
test:
	@echo "🧪 Running tests..."
	docker-compose exec processor python -m pytest tests/ -v

# Clean up everything
clean:
	@echo "🧹 Cleaning up..."
	docker-compose down -v
	docker system prune -f
	@echo "✅ Cleanup complete"

# Install host dependencies for audio capture
install:
	@echo "📦 Installing host dependencies..."
	pip3 install pyaudio numpy webrtcvad soundfile
	@echo "✅ Host dependencies installed"
	@echo "   You can now run: python3 host_audio_capture.py"

# Check system requirements
check:
	@echo "🔍 Checking system requirements..."
	@command -v docker >/dev/null 2>&1 || { echo "❌ Docker not found. Please install Docker Desktop."; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "❌ docker-compose not found."; exit 1; }
	@command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 not found."; exit 1; }
	@echo "✅ System requirements check passed"

# Show status
status:
	@echo "📊 Mike Logger Status:"
	@echo ""
	@echo "Docker Services:"
	docker-compose ps
	@echo ""
	@echo "Data Directory:"
	@ls -la data/ 2>/dev/null || echo "  No data directory found"
	@echo ""
	@echo "Audio Files:"
	@ls -la data/audio/ 2>/dev/null | wc -l | xargs -I {} echo "  {} files"
	@echo ""
	@echo "Transcripts:"
	@ls -la data/transcripts/ 2>/dev/null | wc -l | xargs -I {} echo "  {} files"
	@echo ""
	@echo "Tasks:"
	@ls -la data/tasks/ 2>/dev/null | wc -l | xargs -I {} echo "  {} files"

# Development commands
dev-setup: check install
	@echo "🛠️  Setting up development environment..."
	@if [ ! -f .env ]; then cp .env.example .env; echo "📝 Created .env from template - please edit with your API keys"; fi
	@echo "✅ Development setup complete"

# Production deployment
prod-deploy:
	@echo "🚀 Deploying to production..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Backup data
backup:
	@echo "💾 Backing up data..."
	@mkdir -p backups
	tar -czf backups/mike-logger-$(shell date +%Y%m%d_%H%M%S).tar.gz data/
	@echo "✅ Backup complete: backups/mike-logger-$(shell date +%Y%m%d_%H%M%S).tar.gz"
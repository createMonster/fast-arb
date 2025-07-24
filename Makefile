# Makefile for Funding Rate Arbitrage MVP

.PHONY: help install test lint format clean run monitor check-config test-connections check-spreads

# Default target
help:
	@echo "Available commands:"
	@echo "  install        - Install dependencies"
	@echo "  test          - Run tests"
	@echo "  test-unit     - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  lint          - Run linting"
	@echo "  format        - Format code"
	@echo "  clean         - Clean up generated files"
	@echo "  run           - Run the arbitrage engine"
	@echo "  monitor       - Run in monitor mode (no trading)"
	@echo "  check-config  - Check configuration"
	@echo "  test-connections - Test exchange connections"
	@echo "  check-spreads - Check current funding rate spreads"
	@echo "  setup-env     - Setup environment file"
	@echo "  dev-install   - Install development dependencies"

# Installation
install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt

dev-install: install
	@echo "Installing development dependencies..."
	pip install pytest pytest-asyncio pytest-cov pytest-timeout black flake8 mypy

# Testing
test:
	@echo "Running all tests..."
	pytest

test-unit:
	@echo "Running unit tests..."
	pytest -m "unit or not integration"

test-integration:
	@echo "Running integration tests..."
	pytest -m integration

test-fast:
	@echo "Running fast tests..."
	pytest -m "not slow"

test-coverage:
	@echo "Running tests with coverage..."
	pytest --cov=src --cov-report=html --cov-report=term

# Code quality
lint:
	@echo "Running linting..."
	flake8 src/ tests/ main.py
	mypy src/ --ignore-missing-imports

format:
	@echo "Formatting code..."
	black src/ tests/ main.py

format-check:
	@echo "Checking code formatting..."
	black --check src/ tests/ main.py

# Cleanup
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf logs/*.log
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Environment setup
setup-env:
	@echo "Setting up environment file..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file from template. Please edit it with your credentials."; \
	else \
		echo ".env file already exists."; \
	fi

# Application commands
run:
	@echo "Starting arbitrage engine..."
	python main.py run

monitor:
	@echo "Starting in monitor mode..."
	python main.py run --monitor-only

check-config:
	@echo "Checking configuration..."
	python main.py config-check

test-connections:
	@echo "Testing exchange connections..."
	python main.py test-connections

check-spreads:
	@echo "Checking current funding rate spreads..."
	python main.py check-spreads

check-spreads-btc:
	@echo "Checking BTC funding rate spreads..."
	python main.py check-spreads --symbol BTC-USD

# Development helpers
dev-setup: dev-install setup-env
	@echo "Development environment setup complete!"
	@echo "Next steps:"
	@echo "1. Edit .env file with your credentials"
	@echo "2. Edit config/config.yaml as needed"
	@echo "3. Run 'make test-connections' to verify setup"
	@echo "4. Run 'make monitor' to start monitoring"

dev-test: format-check lint test
	@echo "All development checks passed!"

# Docker commands (if using Docker in the future)
docker-build:
	@echo "Building Docker image..."
	docker build -t fast-arb .

docker-run:
	@echo "Running in Docker..."
	docker run --rm -v $(PWD)/config:/app/config -v $(PWD)/logs:/app/logs fast-arb

# Monitoring and logs
logs:
	@echo "Showing recent logs..."
	tail -f logs/arbitrage.log

logs-error:
	@echo "Showing error logs..."
	grep -i error logs/arbitrage.log | tail -20

# Performance testing
perf-test:
	@echo "Running performance tests..."
	pytest tests/ -m "not slow" --benchmark-only

# Security checks
security-check:
	@echo "Running security checks..."
	bandit -r src/
	safety check

# Documentation
docs:
	@echo "Generating documentation..."
	@echo "Documentation is in README.md"
	@echo "API documentation can be generated with sphinx if needed"

# Release preparation
pre-release: clean format lint test
	@echo "Pre-release checks completed successfully!"
	@echo "Ready for release."

# Quick start for new users
quickstart:
	@echo "🚀 Quick Start Guide:"
	@echo "1. make dev-setup     - Setup development environment"
	@echo "2. make test-connections - Test exchange connections"
	@echo "3. make monitor       - Start monitoring (safe mode)"
	@echo "4. make run          - Start trading (live mode)"
	@echo ""
	@echo "For help: make help"
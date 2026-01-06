.PHONY: install lint fix format test run clean

# Install dependencies
install:
	poetry install

# Check for linting errors
lint:
	poetry run ruff check src/ scripts/

# Auto-fix linting errors
fix:
	poetry run ruff check src/ scripts/ --fix

# Format code
format:
	poetry run ruff format src/ scripts/

# Fix + format in one command
dev: fix format
	@echo "✅ Code fixed and formatted"

# Run API tests
test:
	poetry run python scripts/test_apis.py

# Run the bot
run:
	poetry run python -m src.main

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .ruff_cache 2>/dev/null || true

# Show help
help:
	@echo "Available commands:"
	@echo "  make install  - Install dependencies"
	@echo "  make lint     - Check for linting errors"
	@echo "  make fix      - Auto-fix linting errors"
	@echo "  make format   - Format code with ruff"
	@echo "  make dev      - Fix + format"
	@echo "  make test     - Run API tests"
	@echo "  make run      - Run the bot"
	@echo "  make clean    - Clean cache files"


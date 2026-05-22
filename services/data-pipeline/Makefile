.PHONY: silver gold test lint api docker-up docker-down

# ── Silver layer (PySpark via Docker) ────────────────────────────────────────
docker-up:
	docker compose up -d spark-master spark-worker-1 spark-worker-2

silver: docker-up
	docker compose run --rm spark-submit

docker-down:
	docker compose down

# ── Gold layer (Pandas → Postgres, runs locally) ─────────────────────────────
gold:
	python -m gold.run

gold-table:
	@echo "Usage: make gold-table TABLE=growth_dynamics"
	python -m gold.run --table $(TABLE)

# ── Backend API ───────────────────────────────────────────────────────────────
api:
	uvicorn app.main:app --reload --port 8000

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-gold:
	pytest tests/gold/ -v

test-pipeline:
	pytest tests/pipeline/ -v

# ── Lint & type-check ─────────────────────────────────────────────────────────
lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy gold/ pipeline/ storage/ config/ utils/ app/

# ── Helpers ───────────────────────────────────────────────────────────────────
install:
	pip install -e ".[dev]"

db-test:
	python -m storage.connect

.PHONY: install dev gateway modules test eval lint clean

install:
	pip install -e packages/sdk-python -e gateway -e modules/echo -e modules/weather

dev:
	cd gateway && uvicorn app.main:app --reload --port 8000

gateway:
	cd gateway && uvicorn app.main:app --host 0.0.0.0 --port 8000

modules-echo:
	cd modules/echo && uvicorn main:app --host 0.0.0.0 --port 8001

modules-weather:
	cd modules/weather && uvicorn main:app --host 0.0.0.0 --port 8002

up:
	docker compose up --build

down:
	docker compose down

test:
	pytest tests/ -v

eval:
	python evaluations/runners/intent_eval.py

lint:
	ruff check gateway/ modules/ packages/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

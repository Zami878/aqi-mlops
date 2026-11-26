.PHONY: install test build run fetch validate leaderboard monitor retrain rollback up up-release down

IMAGE ?= aqi-api:dev

install:
	pip install -e ".[dev]"

test:
	ruff check . && ruff format --check .
	pytest -v

build:
	docker build --build-arg GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) -t $(IMAGE) .

run: build
	docker run --rm -p 8000:8000 $(IMAGE)

fetch:
	python -m aqi.data fetch

validate:
	python -m aqi.data validate

leaderboard:
	python -m aqi.models leaderboard --check

monitor:
	python -m aqi.monitor

retrain:
	python -m aqi.retrain run

rollback:
	python -m aqi.retrain rollback

up:
	docker compose -f deploy/docker-compose.yml up -d --build
	@echo "Up. Grafana on GRAFANA_PORT (default 3000), API on API_PORT (default 8000)."

up-release:
	AQI_IMAGE=ghcr.io/zami878/aqi-mlops:latest docker compose -f deploy/docker-compose.yml up -d --no-build

down:
	docker compose -f deploy/docker-compose.yml down

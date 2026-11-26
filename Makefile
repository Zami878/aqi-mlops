.PHONY: install test build run

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

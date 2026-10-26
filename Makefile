# ServicePilot —— 统一命令入口
# 用法: make help

ifeq ($(OS),Windows_NT)
VENV_PY := .venv/Scripts/python.exe
else
VENV_PY := .venv/bin/python
endif

PYTHON  ?= $(if $(wildcard $(VENV_PY)),$(VENV_PY),python)
PORT    ?= 8000
COMPOSE ?= docker compose -f infra/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help install dev up down restart logs ps test lint fmt typecheck check clean

help:
	@echo "ServicePilot - available targets"
	@echo "  make install    install deps (incl. dev tools)"
	@echo "  make dev        run API locally with reload, port $(PORT)"
	@echo "  make up         start compose stack (api/postgres/redis/minio)"
	@echo "  make down       stop and remove compose stack"
	@echo "  make restart    restart compose stack"
	@echo "  make logs       follow compose logs"
	@echo "  make ps         show compose container status"
	@echo "  make test       run pytest"
	@echo "  make lint       ruff check + format check"
	@echo "  make fmt        ruff autofix + format"
	@echo "  make typecheck  mypy type check"
	@echo "  make check      lint + test (used by CI)"
	@echo "  make clean      remove caches"

install:
	$(PYTHON) -m pip install -e ".[dev]"

dev:
	$(PYTHON) -m uvicorn apps.api.main:app --reload --host 0.0.0.0 --port $(PORT)

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

test:
	$(PYTHON) -m pytest -q tests

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

fmt:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

typecheck:
	$(PYTHON) -m mypy apps packages

check: lint test

clean:
	$(PYTHON) -c "import shutil,pathlib;[shutil.rmtree(p,ignore_errors=True) for p in ['build','dist','.pytest_cache','.ruff_cache','.mypy_cache','.coverage','htmlcov']]"
	$(PYTHON) -c "import pathlib,shutil;[shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"

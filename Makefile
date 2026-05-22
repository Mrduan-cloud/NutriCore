.PHONY: help install dev test lint fmt seed demo build up down logs ps clean push

help:
	@echo "NutriCore 常用命令："
	@echo "  make install    安装依赖（本地）"
	@echo "  make dev        本地启动 API (uvicorn --reload)"
	@echo "  make test       运行单元测试"
	@echo "  make lint       静态检查"
	@echo "  make fmt        代码格式化"
	@echo "  make build      构建 Docker 镜像"
	@echo "  make up         docker compose 启动全栈"
	@echo "  make down       docker compose 停服"
	@echo "  make logs       看 api 日志"
	@echo "  make seed       初始化 DB + 知识库 + Demo 数据"
	@echo "  make demo       跑端到端 demo"
	@echo "  make clean      清理临时文件"

install:
	python -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v --tb=short

lint:
	ruff check app tests scripts
	python -c "import ast,sys,pathlib;[ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('.').rglob('*.py')];print('AST OK')"

fmt:
	ruff format app tests scripts

build:
	docker compose build

up:
	docker compose up -d
	@echo "== 服务已起，查看 docs: http://localhost:8000/docs =="

down:
	docker compose down

logs:
	docker compose logs -f api

ps:
	docker compose ps

seed:
	docker compose exec api python -m scripts.seed

demo:
	docker compose exec api python -m scripts.demo --base-url http://localhost:8000 --user demo-001

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache

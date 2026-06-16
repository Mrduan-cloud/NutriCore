# syntax=docker/dockerfile:1.6
# 多阶段构建：第一阶段装依赖，第二阶段拷贝运行时
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU-only PyTorch (exact +cpu 钉版,取自官方 CPU index)与 requirements 在同一 pip pass
# 安装,使 sentence-transformers / FlagEmbedding 的传递依赖 torch 解析到 CPU 构建。
# +cpu 构建不依赖 nvidia-*/triton,直接砍掉约 3.4GB 在 CPU 部署上纯属死重的 GPU 库
# (W12 镜像瘦身;本项目私有化定位为 CPU 部署)。
RUN pip install --prefix=/install --extra-index-url https://download.pytorch.org/whl/cpu \
    --retries 10 --timeout 120 torch==2.12.0+cpu -r requirements.txt
# 砍掉 torch 的 C++ 头文件与测试夹具:推理运行时永不需要,约省 144MB。
RUN rm -rf /install/lib/python3.11/site-packages/torch/test \
           /install/lib/python3.11/site-packages/torch/include


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder /install /usr/local
COPY --chown=app:app . /app

# 模型缓存目录
RUN mkdir -p /app/.cache/models /app/.cache/bm25 && chown -R app:app /app/.cache

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

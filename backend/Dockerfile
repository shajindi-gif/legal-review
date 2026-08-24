FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 系统依赖：
# - libpq5: asyncpg
# - libmagic1: python-magic 文件类型识别
# - poppler-utils: pdf2image
# - fonts-noto-cjk: WeasyPrint 中文 PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libmagic1 poppler-utils fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

# 复制源码
COPY . .

# 沙箱目录
RUN mkdir -p /app/_sandbox

ENV SANDBOX_ROOT=/app/_sandbox

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# syntax=docker/dockerfile:1
# ↑ 使用 BuildKit 的 Dockerfile 前端，才能用 RUN --mount=type=cache

# ============================================================
# 第 1 阶段：builder —— 只负责把依赖装好
# 这一阶段可以很大、可以装编译器、可以留缓存，反正不进最终镜像
# ============================================================
FROM python:3.12 AS builder

# 国内网络：uv 从清华源下载包。能直连 PyPI 就改成 https://pypi.org/simple
ARG UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ARG UV_VERSION=0.13.4

ENV UV_DEFAULT_INDEX=${UV_DEFAULT_INDEX} \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv 是装依赖的工具；装完它只存在于 builder 阶段
RUN pip install --no-cache-dir --index-url "${UV_DEFAULT_INDEX}" "uv==${UV_VERSION}"

WORKDIR /app

# 先拷“依赖清单”，源码变化不会让这一层缓存失效
COPY pyproject.toml uv.lock README.md ./

# 只装第三方依赖，先不装项目本身（--no-install-project）
# --no-dev 是防御性的：本项目的 dev 依赖是 extra，默认就不会装
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 再拷源码，装项目本身（可编辑安装，.pth 指向 /app）
COPY apps ./apps
COPY packages ./packages
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ============================================================
# 第 2 阶段：runtime —— 最终镜像只有这一阶段
# ============================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

# 非 root 用户：容器里的 root 权限很大，能不用就不用
RUN groupadd --gid 1000 app \
&& useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# 从 builder 只搬两样东西：venv 和源码
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app apps ./apps
COPY --chown=app:app packages ./packages
# 迁移脚本（容器启动时要跑 alembic upgrade head）
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./

USER app

EXPOSE 8000

# 健康检查：slim 镜像没有 curl，用 Python 标准库最稳
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

# exec 形式：uvicorn 直接成为 PID 1，才能收到 docker stop 的 SIGTERM
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "20"]

# ServicePilot

企业技术支持 Agent —— FastAPI + Postgres(pgvector) + Redis + S3 兼容存储 + Streamlit 前端。

当前版本 **v0.1**：注册登录、多轮会话、流式回复、按用户限流、Docker 容器化。

## 功能

- **认证**：邮箱密码注册 / 登录，JWT access + refresh 双 token
- **会话与消息**：CRUD、分页、软删除、按用户隔离
- **流式对话**：SSE，带心跳、上游超时重试、并发信号量
- **缓存**：会话列表 Redis cache-aside，按用户版本号整体失效
- **限流**：按用户 60 秒滑动窗口（Redis ZSET + Lua 原子脚本）
- **前端**：Streamlit 最小聊天页（登录 / 会话列表 / 流式显示）
- **部署**：Docker 多阶段构建、非 root、健康检查、优雅停机

## 技术栈

| 层 | 选型 |
| :--- | :--- |
| Web | FastAPI、Uvicorn |
| 数据 | SQLAlchemy 2.x (async)、Postgres 16 + pgvector、Alembic |
| 缓存 / 限流 | Redis 7 |
| 对象存储 | MinIO 兼容（本地用 SILO） |
| 认证 | PyJWT、pwdlib（Argon2） |
| LLM | OpenAI 兼容接口（默认 DeepSeek） |
| 前端 | Streamlit + httpx |

## 架构

```
浏览器 ──▶ Streamlit (:8501) ── HTTP/SSE ──▶ FastAPI (:8000)
                                        │
                ┌──────────────────────┼───────────────────┐
                ▼                      ▼                   ▼
        Postgres 16            Redis 7              MinIO / SILO
        (+ pgvector)          缓存 / 限流             S3 兼容
```

## 快速开始

前置：Python 3.11+、Docker Desktop、`make`、`uv`。

### 1. 配置

```bash
cp .env.example .env
```

编辑 `.env`，至少填 `LLM_API_KEY`（DeepSeek / Qwen / GLM / Kimi 等 OpenAI 兼容服务均可用）。

### 2. 起后端（容器）

```bash
make up
```

- API 文档：http://127.0.0.1:8000/docs
- MinIO 控制台：http://127.0.0.1:9001

容器启动时会自动执行 `alembic upgrade head`。

### 3. 起前端

```bash
make install   # 首次：安装依赖（含 dev 与 web）
make web       # http://localhost:8501
```

### 本机开发

```bash
make up    # 只起依赖服务
make dev   # 本机跑 API，改代码自动重载
make web   # 另开终端跑前端
```

## 常用命令

| 命令 | 作用 |
| :--- | :--- |
| `make up` / `make down` | 起 / 停 compose 全栈 |
| `make restart` / `make logs` / `make ps` | 重启 / 跟日志 / 看状态 |
| `make dev` | 本机跑 API（热重载，8000） |
| `make web` | 跑 Streamlit（8501） |
| `make test` | pytest |
| `make lint` / `make fmt` | 检查 / 自动修格式 |
| `make check` | lint + test（CI 用） |

## 目录结构

```
apps/
api/          FastAPI 应用（routers / services / repositories / schemas）
web/          Streamlit 前端
packages/
core/         配置、LLM 客户端、SSE、Redis、限流、安全
db/           SQLAlchemy 模型与 session
alembic/        数据库迁移
infra/          docker-compose.yml
tests/          pytest
```

## 验收（v0.1）

1. 注册 → 登录
2. 多轮流式对话
3. 重启服务后历史仍在
4. 超过限流阈值返回 429

## 路线图

- v0.2：RAG 知识库、文档上传（MinIO + pgvector）、token 刷新与登出
- v0.3：工具调用、工单流转、人工介入
- 之后：CI/CD、可观测性、评测集

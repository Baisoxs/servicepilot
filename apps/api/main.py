"""ServicePilot API 入口。

M0 阶段只保证进程能起来；/healthz、/readyz、POST /v1/chat(SSE) 在 W1 第 5 步实现。
"""

from fastapi import FastAPI

app = FastAPI(title="ServicePilot API", version="0.1.0")

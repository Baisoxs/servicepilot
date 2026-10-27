"""LLM 客户端：统一封装 OpenAI 兼容接口。

DeepSeek / Qwen / GLM / Kimi 都提供 OpenAI 兼容的 /v1 接口。
换供应商只改 .env 里的 LLM_BASE_URL 和 LLM_MODEL，代码一行不动。
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam

from packages.core.config import get_settings


def get_client() -> OpenAI:
    """按配置创建一个客户端。"""
    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)


def chat(prompt: str, system: str | None = None, temperature: float = 0.2) -> str:
    """发一句话，返回模型的回答。"""
    s = get_settings()

    messages: list[ChatCompletionMessageParam] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = get_client().chat.completions.create(
        model=s.llm_model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


@lru_cache
def get_async_client() -> AsyncOpenAI:
    """异步客户端：给 FastAPI 用，创建一次就复用。"""
    s = get_settings()
    return AsyncOpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)


async def astream(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    """流式输出：模型吐一段，yield 一段。"""
    s = get_settings()

    messages: list[ChatCompletionMessageParam] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    stream = await get_async_client().chat.completions.create(
        model=s.llm_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )

    async for chunk in stream:
        piece = chunk.choices[0].delta.content
        if piece:
            yield piece

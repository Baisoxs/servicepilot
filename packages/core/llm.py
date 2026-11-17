"""LLM 客户端：统一封装 OpenAI 兼容接口。

DeepSeek / Qwen / GLM / Kimi 都提供 OpenAI 兼容的 /v1 接口。
换供应商只改 .env 里的 LLM_BASE_URL 和 LLM_MODEL，代码一行不动。

W3 起 astream 多了三层保护：
- Semaphore：限制同时打到上游的请求数（在途请求）
- asyncio.timeout：单次尝试超时；拿到信号量之后才开始计时
- 指数退避 + 随机抖动：只重试「还没吐过字」的可重试错误
"""

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from functools import lru_cache

import openai
from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam

from packages.core.config import get_settings

logger = logging.getLogger(__name__)

# 可重试的 HTTP 状态码：请求超时 / 冲突 / 过早 / 限流；5xx 另外判断
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429})

# asyncio 原语会绑定到第一个使用它的事件循环。pytest 每个测试会新建 loop，
# 所以记住信号量属于哪个 loop，换了 loop 就重建，避免 "bound to a different event loop"。
_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(get_settings().llm_max_concurrency)
        _semaphore_loop = loop
    return _semaphore


def _is_retryable(exc: BaseException) -> bool:
    """这个错误等一会儿重试有没有意义？空号（4xx）不重试，占线（429/5xx/超时）重试。"""
    if isinstance(exc, TimeoutError):  # isinstance(对象, 类) 用来判断对象是不是某个类的实例
        return True
    if isinstance(exc, openai.APIConnectionError):
        return True
    # getattr(对象, "属性名", 默认值)。安全地获取对象的属性
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS or status >= 500
    return False


def _backoff_delay(attempt: int) -> float:
    """full jitter：在 0 ~ min(上限, 基数 * 2**attempt) 之间随机。"""
    s = get_settings()
    ceiling = min(s.llm_retry_max_delay, s.llm_retry_base_delay * (2**attempt))
    return random.uniform(0, ceiling)  # 全抖动（Full Jitter）


def get_client() -> OpenAI:
    """按配置创建一个同步客户端。"""
    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)


def chat(prompt: str, system: str | None = None, temperature: float = 0.2) -> str:
    """发一句话，返回模型的回答。"""
    s = get_settings()

    # ChatCompletionMessageParam 是 OpenAI 官方 SDK 提供的类型，
    # 确保你往列表里塞的字典格式（比如 {"role": "...", "content": "..."}）是合法的，
    # 拼写错了编辑器会报警。
    messages: list[ChatCompletionMessageParam] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # 调用标准的 .chat.completions.create() 接口发起网络请求
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


async def _open_stream(
    messages: list[ChatCompletionMessageParam],
    temperature: float,
):
    """真正向上游发起流式请求。

    单独抽出来是给测试用的「接缝」：测试里 monkeypatch 这个函数，
    就能伪造成功、失败、超时、吐一半断掉的流，不用连真实 API。
    """
    s = get_settings()
    return await get_async_client().chat.completions.create(
        model=s.llm_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )


async def astream(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    *,
    timeout_s: float | None = None,
    max_retries: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> AsyncIterator[str]:
    """流式输出：模型吐一段，yield 一段。

    额外的关键字参数默认从配置读，主要是给测试覆盖用的。
    """
    s = get_settings()
    timeout = timeout_s if timeout_s is not None else s.llm_timeout_s
    retries = max_retries if max_retries is not None else s.llm_max_retries
    sem = semaphore if semaphore is not None else _get_semaphore()

    messages: list[ChatCompletionMessageParam] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    attempt = 0  # 记录重试次数
    while True:
        # 记录是否已经往外吐过字了（这个变量是后面防重复的核心）
        yielded_any = False
        try:
            # 先排队拿车位，拿到之后才开始计时：排队时间不算模型超时
            async with sem:
                async with asyncio.timeout(timeout):
                    stream = await _open_stream(messages, temperature)
                    # async with 保证异常/提前退出时关闭上游连接，就算突发异常退出了
                    # 也不会把大模型的 API 连接池给占满
                    async with stream:
                        async for chunk in stream:
                            piece = chunk.choices[0].delta.content
                            if piece:
                                # 一旦吐过字，后面再失败就不能重试，否则内容会重复
                                yielded_any = True
                                yield piece
            return
        except asyncio.CancelledError:
            # 客户端断开 / 服务关闭：取消信号必须原样上抛，不能当失败重试
            raise
        except Exception as exc:
            if yielded_any or attempt >= retries or not _is_retryable(exc):
                raise
            delay = _backoff_delay(attempt)
            logger.warning(
                "LLM 调用失败，%.2fs 后重试（第 %d/%d 次）：%s",
                delay,
                attempt + 1,
                retries,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
            attempt += 1

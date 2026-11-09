"""通用响应结构。"""

from typing import Generic, TypeVar

from pydantic import BaseModel

# T 是“占位类型”：Page 不关心 items 里装的是什么，用的人再指定。
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """分页响应。

    items  当前这一页的数据
    total  符合条件的总条数（不是这一页的条数）
    limit  每页最多几条
    offset 从第几条开始
    """

    items: list[T]
    total: int
    limit: int
    offset: int

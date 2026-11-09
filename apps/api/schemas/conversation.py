"""会话接口的请求 / 响应结构。"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# 标题的统一规则：去掉首尾空格后，长度 1~255。
# strip_whitespace 会在检查长度之前先执行，所以全是空格的标题会变成 "" 再被拒绝。
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"title": "如何重置密码"}]})

    title: Title = Field(examples=["如何重置密码"])


class ConversationUpdate(BaseModel):
    # 目前只有 title 一个可改字段，所以 PATCH 也要求必须带 title。
    model_config = ConfigDict(json_schema_extra={"examples": [{"title": "密码重置（已解决）"}]})

    title: Title = Field(examples=["密码重置（已解决）"])


class ConversationOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "0b6f7c1e-2d3a-4b5c-9d8e-1f2a3b4c5d6e",
                    "title": "如何重置密码",
                    "created_at": "2026-11-09T08:00:00Z",
                    "updated_at": "2026-11-09T08:05:00Z",
                }
            ]
        },
    )

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

"""消息接口的请求 / 响应结构。"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from packages.db.models import MessageRole

# 消息正文的统一规则：去掉首尾空白后，长度 1~4000。
Content = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class MessageCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"role": "user", "content": "我的密码重置链接失效了"}]}
    )

    role: MessageRole = MessageRole.user
    content: Content = Field(examples=["我的密码重置链接失效了"])


class MessageOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                    "conversation_id": "0b6f7c1e-2d3a-4b5c-9d8e-1f2a3b4c5d6e",
                    "role": "user",
                    "content": "我的密码重置链接失效了",
                    "created_at": "2026-11-09T08:00:00Z",
                }
            ]
        },
    )

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime

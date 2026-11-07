"""认证接口的请求 / 响应结构（Pydantic 模型）。

这些类只描述“数据长什么样”，不碰数据库、不写业务逻辑。
FastAPI 用它们做三件事：
    1. 校验请求参数，不合格直接 422
    2. 过滤响应字段，多余字段不会漏出去
    3. 生成 /docs 里的接口文档
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """注册请求。密码长度在这里就校验，不合格的请求到不了 service。"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """登录请求。

    密码不限制长度：把规则写在这里等于告诉攻击者密码格式，
    而且早期用户的短密码会被无辜挡住。
    """

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """换新 token 的请求。refresh_token 放在请求体，不放 URL。"""

    refresh_token: str


class TokenResponse(BaseModel):
    """登录 / 换 token 成功的响应。"""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class UserOut(BaseModel):
    """对外公开的用户信息。

    绝对不包含 password_hash：响应 schema 决定了哪些字段能离开服务器。
    from_attributes=True 允许 Pydantic 直接从 ORM 对象身上读属性。
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    created_at: datetime

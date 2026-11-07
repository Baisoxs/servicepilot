"""认证接口：注册、登录、换 token、查看当前用户。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user
from apps.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from apps.api.services.auth import AuthService
from packages.db.models import User
from packages.db.session import get_session

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> User:
    """注册新用户。邮箱重复返回 409。"""
    return await AuthService(session).register(body.email, body.password)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """用邮箱密码换 access + refresh token。"""
    access_token, refresh_token = await AuthService(session).login(body.email, body.password)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """用 refresh token 换一对新 token。"""
    access_token, refresh_token = await AuthService(session).refresh(body.refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """返回当前登录用户，用来验证鉴权链路是否打通。"""
    return current_user

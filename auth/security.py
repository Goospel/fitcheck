"""C1 · 비밀번호 해시 · 토큰 · 인증 의존성

⚠️ **평문 비밀번호는 어디에도 남기지 않는다** — 저장·로그·에러 메시지 전부
(CLAUDE.md 6절). 이 파일 밖으로 평문이 나가는 경로를 만들지 않는다.
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from db.models import User
from db.session import get_session

# bcrypt 5.0 은 이걸 넘기면 **예외를 던진다**(조용히 자르지 않는다).
# 한글은 UTF-8 3바이트라 24자면 이미 72바이트다 — 안 막으면 사용자가 500 을 본다.
BCRYPT_MAX_BYTES = 72

_ALGO = "HS256"
_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    if len(plain.encode()) > BCRYPT_MAX_BYTES:
        raise AppError(
            "PASSWORD_TOO_LONG",
            f"비밀번호가 너무 깁니다 (한글 {BCRYPT_MAX_BYTES // 3}자·영문 {BCRYPT_MAX_BYTES}자까지)",
            400,
        )
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """틀렸는지 여부만 돌려준다. 이유(해시 오염·길이 초과)를 밖으로 흘리지 않는다."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=settings.jwt_expire_hours)},
        settings.jwt_secret,
        algorithm=_ALGO,
    )


def decode_token(token: str) -> uuid.UUID:
    """망가진·위조된·만료된 토큰을 전부 401 하나로 떨어뜨린다."""
    try:
        return uuid.UUID(jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise AppError("INVALID_TOKEN", "다시 로그인해 주세요", 401) from None


async def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_session),
) -> User:
    """인증이 필요한 라우터는 `user: User = Depends(current_user)` 로 받는다."""
    if cred is None:
        raise AppError("UNAUTHORIZED", "로그인이 필요합니다", 401)
    user = await db.get(User, decode_token(cred.credentials))
    if user is None:
        # 토큰은 살아 있는데 계정이 지워진 경우 (C5)
        raise AppError("UNAUTHORIZED", "로그인이 필요합니다", 401)
    return user

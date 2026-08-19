"""C1 · 가입 · 로그인 API

⚠️ **`POST /auth/check` 가 이 묶음의 핵심이다.** PRD 는 가입/로그인 탭을 두지
않고 「이메일을 먼저 받아 서버가 판단해 분기」하는 설계다 — 프론트 로그인 화면
4단계가 이 응답 하나에 걸려 있다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import create_token, current_user, hash_password, verify_password
from core.errors import AppError
from core.schema import Schema
from db.models import User
from db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

# 라이브러리를 하나 더 붙이는 대신 패턴 한 줄. 형식 검증은 어차피 오타를 거르는 용도다
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)]

# ⚠️ 최소 8자는 PRD 에 없다 — docs/open-questions.md T7. 바꾸려면 여기 한 곳만 고친다
Password = Annotated[str, Field(min_length=8, max_length=128)]


def _normalize(email: str) -> str:
    """대소문자만 다른 중복 계정을 막는다. 저장·조회 양쪽에서 항상 거친다."""
    return email.strip().lower()


class CheckRequest(Schema):
    email: Email


class CheckResponse(Schema):
    exists: bool


class SignupRequest(Schema):
    email: Email
    password: Password
    is_over_14: bool      # 만 14세 미만 가입 차단 — 화면의 동의 체크


class LoginRequest(Schema):
    email: Email
    password: str         # 로그인은 길이 규칙을 걸지 않는다. 규칙이 바뀌어도 기존 사용자가 막히면 안 된다


class TokenResponse(Schema):
    token: str
    user_id: uuid.UUID


class MeResponse(Schema):
    user_id: uuid.UUID
    email: str


@router.post("/check")
async def check(body: CheckRequest, db: AsyncSession = Depends(get_session)) -> CheckResponse:
    """이메일이 이미 있는지. 프론트는 이걸로 「비밀번호 입력」과 「비밀번호 설정」을 가른다."""
    found = await db.scalar(select(User.id).where(User.email == _normalize(body.email)))
    return CheckResponse(exists=found is not None)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_session)) -> TokenResponse:
    """가입하면 토큰을 바로 준다 — 가입 직후 로그인을 또 시키지 않는다."""
    if not body.is_over_14:
        raise AppError("AGE_RESTRICTED", "만 14세 미만은 가입할 수 없습니다", 400)

    user = User(email=_normalize(body.email), password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # 미리 SELECT 로 확인하지 않는다 — 확인과 삽입 사이의 경쟁을 유니크 제약이 대신 막는다
        await db.rollback()
        raise AppError("EMAIL_TAKEN", "이미 가입된 이메일입니다", 409) from None

    return TokenResponse(token=create_token(user.id), user_id=user.id)


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_session)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == _normalize(body.email)))
    if user is None or not verify_password(body.password, user.password_hash):
        # 계정이 없는 것과 비밀번호가 틀린 것을 **같은 응답으로** 낸다
        raise AppError("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다", 401)
    return TokenResponse(token=create_token(user.id), user_id=user.id)


@router.get("/me")
async def me(user: User = Depends(current_user)) -> MeResponse:
    return MeResponse(user_id=user.id, email=user.email)

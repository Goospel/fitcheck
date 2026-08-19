"""C1 · 가입 · 로그인 API

⚠️ **`POST /auth/check` 가 이 묶음의 핵심이다.** PRD 는 가입/로그인 탭을 두지
않고 「이메일을 먼저 받아 서버가 판단해 분기」하는 설계다 — 프론트 로그인 화면
4단계가 이 응답 하나에 걸려 있다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import AfterValidator, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import create_token, current_user, hash_password, verify_password
from core.errors import AppError
from core.schema import Schema
from db.models import User
from db.session import get_session
from images import storage

router = APIRouter(prefix="/auth", tags=["auth"])

# 라이브러리를 하나 더 붙이는 대신 패턴 한 줄. 형식 검증은 어차피 오타를 거르는 용도다
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)]

def _two_kinds(pw: str) -> str:
    """PRD 7.8 — 영문·숫자·기호 중 **2종 이상**. 특수문자를 강제하지는 않는다."""
    영문 = {c for c in pw if "a" <= c.lower() <= "z"}
    숫자 = {c for c in pw if c.isdigit()}
    # 그 밖은 전부 「기호」다 — 한글도 여기 들어간다.
    # `isalnum()` 은 한글에 True 라 한글+숫자를 1종으로 잘못 센다
    기호 = set(pw) - 영문 - 숫자
    종류 = sum(map(bool, (영문, 숫자, 기호)))
    if 종류 < 2:
        raise ValueError("영문·숫자·기호 중 2종 이상을 섞어 주세요")
    return pw


# PRD 7.8 — 8자 이상 + 2종 조합. 상한 128 은 우리가 정한 값이다 (bcrypt 72바이트는 별도)
Password = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(_two_kinds)]


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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> None:
    """계정 삭제. 프로필·의류·피팅 결과가 외래키 CASCADE 로 같이 사라진다.

    ⚠️ **저장소의 사진을 먼저 지운다.** 전신 사진이라 계정을 지웠는데 남아 있으면
    그게 사고다. 순서가 반대면 — 행을 먼저 지우고 저장소에서 실패하면 — 누구의
    것인지 알 방법 없이 파일만 남는다. 이 순서면 실패해도 다시 시도할 수 있다.

    로그아웃 엔드포인트는 두지 않는다. JWT 는 서버에 상태가 없어 할 일이 없고,
    프론트가 토큰을 버리면 그게 로그아웃이다.
    """
    await storage.remove_user_photos(user.id)
    await db.delete(user)
    await db.commit()

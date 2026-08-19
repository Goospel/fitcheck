"""B2 · 프로필 API

1단계 필수 3개(키·몸무게·성별) + 2단계 선택(실측 4개 · 선호 핏). `PUT` 하나로
받는다 — 화면은 두 단계지만 API 를 나누면 「1단계만 저장된 상태」를 양쪽이 따로
관리해야 한다.

⚠️ **비어 있는 치수 = 「추정」이다** (db/models.py 설계 판단 ②). A4 추정기가
   아직 없어 값은 `null` 이지만, 출처 자리는 지금부터 응답에 있다 — 프론트가
   표시를 나눌 수 있어야 하고, A4 가 붙으면 값만 채워진다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import current_user
from core.errors import AppError
from core.schema import Schema
from db.models import Profile, User
from db.session import get_session
from fit.grade import GRADE_ORDER

router = APIRouter(prefix="/profile", tags=["profile"])

# 정확도 n/5 의 분자를 이루는 항목 — 실측 4개 + 선호 핏 1개 (CLAUDE.md 1절)
MEASUREMENTS = ("shoulder", "chest", "waist", "arm")

# CLAUDE.md 1절 확정 상수. 치수 추정 용도로만 쓴다
GENDERS = ("남성", "여성", "밝히지 않음")

Cm = Annotated[float | None, Field(default=None, gt=0, le=300)]


class Measurement(Schema):
    value: float | None
    source: str           # 실측 | 추정


class ProfileRequest(Schema):
    height: int = Field(ge=100, le=220)
    weight: int = Field(ge=30, le=200)
    gender: Literal[GENDERS]

    shoulder: Cm
    chest: Cm
    waist: Cm
    arm: Cm
    # 등급 문구를 새로 타이핑하지 않는다 — fit.grade 가 유일한 출처다
    preferred_grade: Literal[GRADE_ORDER] | None = None


class ProfileResponse(Schema):
    height: int
    weight: int
    gender: str
    measurements: dict[str, Measurement]
    preferred_grade: str | None
    accuracy: int          # 0 ~ 5


def _to_response(p: Profile) -> ProfileResponse:
    치수 = {
        이름: Measurement(
            value=getattr(p, 이름),
            source="실측" if getattr(p, 이름) is not None else "추정",
        )
        for 이름 in MEASUREMENTS
    }
    return ProfileResponse(
        height=p.height,
        weight=p.weight,
        gender=p.gender,
        measurements=치수,
        preferred_grade=p.preferred_grade,
        accuracy=sum(1 for m in 치수.values() if m.source == "실측")
        + (1 if p.preferred_grade else 0),
    )


@router.get("")
async def read(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> ProfileResponse:
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise AppError("PROFILE_NOT_FOUND", "프로필을 먼저 입력해 주세요", 404)
    return _to_response(profile)


@router.put("")
async def upsert(
    body: ProfileRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    """전체 교체다. 안 보낸 치수는 지워지고 다시 「추정」으로 돌아간다."""
    profile = await db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)

    profile.height = body.height
    profile.weight = body.weight
    profile.gender = body.gender
    profile.preferred_grade = body.preferred_grade
    for 이름 in MEASUREMENTS:
        setattr(profile, 이름, getattr(body, 이름))

    await db.commit()
    return _to_response(profile)

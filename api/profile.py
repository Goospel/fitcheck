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
from fit.estimate import estimate_body
from fit.grade import PREFERRED_GRADES
from images import storage

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
    # 등급 문구를 새로 타이핑하지 않는다 — fit.grade 가 유일한 출처다.
    # 5종이 아니라 4종이다 — 「너무 작음」을 선호할 사람은 없다 (PRD 7.2)
    preferred_grade: Literal[PREFERRED_GRADES] | None = None


class ProfileResponse(Schema):
    height: int
    weight: int
    gender: str
    measurements: dict[str, Measurement]
    preferred_grade: str | None
    accuracy: int          # 0 ~ 5
    # 전신 사진 (D1). **PUT 으로는 안 바뀐다** — 업로드 엔드포인트가 붙인다
    photo_path: str | None
    photo_url: str | None      # 비공개 버킷이라 조회 때마다 새로 서명한다


def resolved_measurements(p: Profile) -> dict[str, float]:
    """계산에 쓸 치수 4종 — **실측이 있으면 실측이 이기고, 빈칸만 A4 가 채운다.**

    ⚠️ 출처(실측/추정)는 여기서 안 돌려준다. 값과 출처를 같이 들고 다니는 것은
       `Measurement`(응답)와 `Body.measured`(계산)의 일이고, 둘의 판정 기준은
       **「직접 넣었는가」 하나**다 — 이 함수가 그걸 흐리면 배지가 거짓말을 한다.
    """
    추정 = estimate_body(p.height, p.weight, p.gender)
    return {
        이름: getattr(p, 이름) if getattr(p, 이름) is not None else getattr(추정, 이름)
        for 이름 in MEASUREMENTS
    }


async def _to_response(p: Profile) -> ProfileResponse:
    값 = resolved_measurements(p)
    치수 = {
        이름: Measurement(
            value=값[이름],
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
        photo_path=p.photo_path,
        photo_url=(await storage.signed_urls([p.photo_path])).get(p.photo_path),
    )


@router.get("")
async def read(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> ProfileResponse:
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise AppError("PROFILE_NOT_FOUND", "프로필을 먼저 입력해 주세요", 404)
    return await _to_response(profile)


@router.put("")
async def upsert(
    body: ProfileRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    """전체 교체다. 안 보낸 치수는 지워지고 다시 「추정」으로 돌아간다.

    ⚠️ **사진은 이 요청에 실리지 않는다.** 치수를 고칠 때마다 전신 사진이 사라지면
       안 되고, 사진은 `PUT /photos/profile` 이 따로 갈아 끼운다.
    """
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
    return await _to_response(profile)

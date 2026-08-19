"""B4 · 핏 분석 API + F-10 · 사이즈 비교

계산은 전부 `fit/` 에 있다. 여기는 **DB 에서 꺼내 넘기고 결과를 돌려주는 층**이고,
판정 로직을 여기에 새로 쓰지 않는다.

⚠️ **A4(치수 추정기)가 아직 없다.** 가슴·어깨를 직접 입력하지 않은 프로필은
   리포트를 낼 수 없다 — 지어낸 값으로 채우는 대신 명시적으로 거절한다
   (docs/open-questions.md Q3).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.profile import MEASUREMENTS
from auth.security import current_user
from core.errors import AppError
from core.schema import Schema
from db.models import Fitting, Garment, Profile, User
from db.session import get_session
from fit.compare import SizeComparison, compare_sizes
from fit.report import Body, FitReport
from fit.report import Garment as FitGarment
from fit.report import build_report

router = APIRouter(prefix="/fittings", tags=["fittings"])

# 한 옷에 사이즈가 이만큼 있을 일이 없다. 요청 크기 상한일 뿐 제품 상수가 아니다
MAX_COMPARE = 10


class FittingRequest(Schema):
    garment_id: uuid.UUID


class FittingResponse(Schema):
    id: uuid.UUID
    garment_id: uuid.UUID
    report: FitReport        # 계약 2 그대로 중첩한다
    created_at: datetime


class CompareRequest(Schema):
    garment_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_COMPARE)


async def _body_of(user: User, db: AsyncSession) -> Body:
    """프로필을 계산용 `Body` 로. 없거나 부족하면 여기서 끊는다."""
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise AppError("PROFILE_NOT_FOUND", "프로필을 먼저 입력해 주세요", 404)
    if profile.chest is None or profile.shoulder is None:
        # A4 가 붙으면 이 자리에서 추정값을 채운다. 그때까지는 거절이 정직하다
        raise AppError(
            "MEASUREMENTS_REQUIRED", "가슴둘레와 어깨너비를 프로필에 입력해 주세요", 400
        )
    return Body(
        chest=profile.chest,
        shoulder=profile.shoulder,
        waist=profile.waist,
        arm=profile.arm,
        measured=frozenset(n for n in MEASUREMENTS if getattr(profile, n) is not None),
        preferred_grade=profile.preferred_grade,
    )


def _to_fit(g: Garment) -> FitGarment:
    return FitGarment(
        chest_width=g.chest_width,
        shoulder=g.shoulder,
        length=g.length,
        waist_width=g.waist_width,
        sleeve=g.sleeve,
        stretch=g.stretch,
    )


async def _owned(ids: list[uuid.UUID], user: User, db: AsyncSession) -> dict[uuid.UUID, Garment]:
    """내 의류만. 남의 것이 섞이면 「없다」로 답한다 — 존재 여부를 흘리지 않는다."""
    rows = await db.scalars(
        select(Garment).where(Garment.id.in_(ids), Garment.user_id == user.id)
    )
    found = {g.id: g for g in rows}
    if len(found) != len(set(ids)):
        raise AppError("GARMENT_NOT_FOUND", "등록된 의류를 찾을 수 없습니다", 404)
    return found


@router.post("/compare")
async def compare(
    body: CompareRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> SizeComparison:
    """같은 옷의 여러 사이즈를 한 응답에. **저장하지 않는다** — 계산을 여러 번 돌릴 뿐이다."""
    found = await _owned(body.garment_ids, user, db)
    사이즈별 = {found[i].size_name: _to_fit(found[i]) for i in body.garment_ids}
    if len(사이즈별) != len(body.garment_ids):
        # 사이즈명이 겹치면 조용히 하나로 합쳐진다. 합치는 대신 알려준다
        raise AppError("DUPLICATE_SIZE_NAME", "사이즈명이 겹칩니다", 400)
    return compare_sizes(await _body_of(user, db), 사이즈별)


@router.post("", status_code=status.HTTP_201_CREATED)
async def analyze(
    body: FittingRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> FittingResponse:
    """프로필 + 의류 → 리포트. 결과를 **그 시점 스냅샷으로** 저장한다."""
    garment = (await _owned([body.garment_id], user, db))[body.garment_id]
    report = build_report(await _body_of(user, db), _to_fit(garment))

    fitting = Fitting(
        user_id=user.id,
        garment_id=garment.id,
        report=report.model_dump(by_alias=True),   # DB 에서도 프론트와 같은 키로 읽히게
    )
    db.add(fitting)
    await db.commit()
    return FittingResponse(
        id=fitting.id, garment_id=garment.id, report=report, created_at=fitting.created_at
    )


@router.get("/{fitting_id}")
async def read(
    fitting_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> FittingResponse:
    fitting = await db.scalar(
        select(Fitting).where(Fitting.id == fitting_id, Fitting.user_id == user.id)
    )
    if fitting is None:
        raise AppError("FITTING_NOT_FOUND", "결과를 찾을 수 없습니다", 404)
    return FittingResponse(
        id=fitting.id,
        garment_id=fitting.garment_id,
        report=FitReport.model_validate(fitting.report),
        created_at=fitting.created_at,
    )

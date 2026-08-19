"""B4 · 핏 분석 + F-10 · 사이즈 비교 + B5 · 히스토리 + B6 · 결과 조회

계산은 전부 `fit/` 에 있다. 여기는 **DB 에서 꺼내 넘기고 결과를 돌려주는 층**이고,
판정 로직을 여기에 새로 쓰지 않는다.

⚠️ **A4(치수 추정기)가 아직 없다.** 가슴·어깨를 직접 입력하지 않은 프로필은
   리포트를 낼 수 없다 — 지어낸 값으로 채우는 대신 명시적으로 거절한다
   (docs/open-questions.md Q3).
"""

import uuid
from collections import Counter
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.profile import MEASUREMENTS
from auth.security import current_user
from core.errors import AppError
from core.schema import Schema
from db.models import FITTING_STATUSES, REPORT_ONLY, Fitting, Garment, ImageJob, Profile, User
from db.session import get_session
from fit.compare import SizeComparison, compare_sizes
from fit.report import Body, FitReport
from fit.report import Garment as FitGarment
from fit.report import build_report

router = APIRouter(prefix="/fittings", tags=["fittings"])

# 한 옷에 사이즈가 이만큼 있을 일이 없다. 요청 크기 상한일 뿐 제품 상수가 아니다
MAX_COMPARE = 10


class GarmentBrief(Schema):
    """목록을 그리려고 의류를 하나씩 다시 물어보게 하지 않는다"""

    id: uuid.UUID
    kind: str
    size_name: str
    photo_path: str | None


class FittingResponse(Schema):
    """B6 · 이미지 + 리포트 통합. **이미지가 없어도 성립한다** (F-09)"""

    id: uuid.UUID
    status: str                  # 계약 3 — 대기/생성중/완료/실패/리포트만
    garment: GarmentBrief
    report: FitReport            # 계약 2 그대로 중첩한다
    image_path: str | None       # 생성 전·실패 시 None
    created_at: datetime


class HistoryResponse(Schema):
    items: list[FittingResponse]
    counts: dict[str, int]       # 뱃지용. **거르기와 무관하게 항상 전체를 센다**


class FittingRequest(Schema):
    garment_id: uuid.UUID


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


def _view(fitting: Fitting, garment: Garment, job_status: str | None) -> FittingResponse:
    return FittingResponse(
        id=fitting.id,
        # 잡이 없다 = 사진 없이 만든 리포트다. 없음 자체가 상태다
        status=job_status or REPORT_ONLY,
        garment=GarmentBrief.model_validate(garment),
        report=FitReport.model_validate(fitting.report),
        image_path=fitting.image_path,
        created_at=fitting.created_at,
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


async def _reusable(
    user: User, garment: Garment, report: FitReport, db: AsyncSession
) -> FittingResponse | None:
    """D6 · 이미 같은 걸 만들어 뒀으면 그걸 돌려준다. 없으면 None.

    생성 1건이 **최대 10분 + 유료 API 호출**이다 (plan.md D6). 시연 중 같은 조합을
    두 번 누르면 그대로 비용이고, 심사위원 앞에서 10분을 기다리는 사고가 난다.
    돌고 있는 잡을 두 번 큐에 넣는 것도 여기서 막힌다.

    ⚠️ **판정이 같을 때만 같은 것이다.** (사용자·의류) 만 보면 프로필이 바뀌어
       판정이 달라졌는데 옛 결과를 돌려주게 되고, 사용자는 틀린 사이즈를 산다.
       리포트가 곧 입력값의 지문이라 따로 해시를 두지 않는다.
    """
    rows = (
        await db.execute(
            select(Fitting, ImageJob.status)
            .outerjoin(ImageJob, ImageJob.fitting_id == Fitting.id)
            .where(Fitting.user_id == user.id, Fitting.garment_id == garment.id)
        )
    ).all()
    # 정렬하지 않는다 — 판정이 같은 행끼리는 서로 구분할 이유가 없다

    지문 = report.model_dump(by_alias=True)
    for fitting, job_status in rows:
        # ⚠️ 실패한 것을 돌려주면 사용자가 **영영 다시 시도할 수 없다**
        if job_status == "실패":
            continue
        if fitting.report == 지문:
            return _view(fitting, garment, job_status)
    return None


@router.get("")
async def history(
    status: Literal[FITTING_STATUSES] | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> HistoryResponse:
    """B5 · 내 피팅 목록 + 상태별 개수.

    생성이 10분 걸리는 이상 **결과를 나중에 찾을 유일한 경로**다 (PRD 7.5).
    개수는 거르기와 무관하게 전체를 센다 — 헤더 뱃지가 필터를 따라가면 안 된다.
    """
    rows = (
        await db.execute(
            select(Fitting, Garment, ImageJob.status)
            .join(Garment, Garment.id == Fitting.garment_id)
            .outerjoin(ImageJob, ImageJob.fitting_id == Fitting.id)
            .where(Fitting.user_id == user.id)
            .order_by(Fitting.created_at.desc())
        )
    ).all()

    # ponytail: 전부 읽어 파이썬에서 세고 거른다. 한 사람의 피팅이 수백 건을
    # 넘기면 개수는 GROUP BY 로, 거르기는 WHERE 로 내린다
    보이는것 = [_view(f, g, s) for f, g, s in rows]
    개수 = Counter(v.status for v in 보이는것)

    return HistoryResponse(
        items=[v for v in 보이는것 if status is None or v.status == status],
        counts={s: 개수.get(s, 0) for s in FITTING_STATUSES},
    )


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


@router.post("", status_code=201)
async def analyze(
    body: FittingRequest,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> FittingResponse:
    """프로필 + 의류 → 리포트. 결과를 **그 시점 스냅샷으로** 저장한다.

    이미 같은 판정을 만들어 뒀으면 새로 만들지 않고 그것을 돌려준다 (D6).
    **만들었으면 201, 재사용이면 200** — 프론트가 「생성 중」 스피너를 띄울지 여기서 가른다.
    """
    garment = (await _owned([body.garment_id], user, db))[body.garment_id]
    report = build_report(await _body_of(user, db), _to_fit(garment))

    기존 = await _reusable(user, garment, report, db)
    if 기존 is not None:
        response.status_code = 200
        return 기존

    fitting = Fitting(
        user_id=user.id,
        garment_id=garment.id,
        report=report.model_dump(by_alias=True),   # DB 에서도 프론트와 같은 키로 읽히게
    )
    db.add(fitting)

    # D4 · 두 사진(인물·제품컷)이 다 있어야 이미지를 만든다. 하나라도 없으면
    # 잡을 만들지 않는다 — 없음 자체가 「리포트만」이라는 상태다 (REPORT_ONLY)
    profile_photo = (
        await db.execute(select(Profile.photo_path).where(Profile.user_id == user.id))
    ).scalar_one()
    job_status = None
    if profile_photo and garment.photo_path:
        await db.flush()   # ImageJob.fitting_id 가 가리킬 fitting.id 를 미리 채운다
        db.add(ImageJob(fitting_id=fitting.id))
        job_status = "대기"

    await db.commit()
    return _view(fitting, garment, job_status)


@router.get("/{fitting_id}")
async def read(
    fitting_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> FittingResponse:
    """B6 · 결과 조회. 이미지가 없거나 생성이 실패해도 리포트는 그대로 나온다."""
    row = (
        await db.execute(
            select(Fitting, Garment, ImageJob.status)
            .join(Garment, Garment.id == Fitting.garment_id)
            .outerjoin(ImageJob, ImageJob.fitting_id == Fitting.id)
            .where(Fitting.id == fitting_id, Fitting.user_id == user.id)
        )
    ).first()
    if row is None:
        raise AppError("FITTING_NOT_FOUND", "결과를 찾을 수 없습니다", 404)
    return _view(*row)

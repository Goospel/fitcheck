"""B4 · 핏 분석 + F-10 · 사이즈 비교 + B5 · 히스토리 + B6 · 결과 조회

계산은 전부 `fit/` 에 있다. 여기는 **DB 에서 꺼내 넘기고 결과를 돌려주는 층**이고,
판정 로직을 여기에 새로 쓰지 않는다.

⚠️ **실측을 안 넣은 프로필도 리포트를 받는다** — 빈 치수는 A4(`fit/estimate.py`)가
   사이즈코리아 앵커로 채운다. 어디까지가 추정인지는 응답의 `confidence` 가 말한다.
"""

import uuid
from collections import Counter
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.profile import MEASUREMENTS, resolved_measurements
from auth.security import current_user
from core.errors import AppError
from core.schema import Schema
from db.models import FITTING_STATUSES, REPORT_ONLY, Fitting, Garment, ImageJob, Profile, User
from db.session import get_session
from fit.compare import SizeComparison, compare_sizes
from fit.report import Body, FitReport
from fit.report import Garment as FitGarment
from fit.report import build_report
from images import storage

router = APIRouter(prefix="/fittings", tags=["fittings"])

# 한 옷에 사이즈가 이만큼 있을 일이 없다. 요청 크기 상한일 뿐 제품 상수가 아니다
MAX_COMPARE = 10


class GarmentBrief(Schema):
    """목록을 그리려고 의류를 하나씩 다시 물어보게 하지 않는다"""

    id: uuid.UUID
    kind: str
    size_name: str
    photo_path: str | None
    photo_url: str | None = None       # 비공개 버킷이라 조회 때마다 새로 서명한다


class FittingResponse(Schema):
    """B6 · 이미지 + 리포트 통합. **이미지가 없어도 성립한다** (F-09)"""

    id: uuid.UUID
    status: str                  # 계약 3 — 대기/생성중/완료/실패/리포트만
    garment: GarmentBrief
    report: FitReport            # 계약 2 그대로 중첩한다
    image_path: str | None       # 생성 전·실패 시 None
    image_url: str | None = None # 서명 URL. 생성 전·실패 시 None
    created_at: datetime

    # ⚠️ 잡의 `error` 는 **일부러 안 내보낸다.** 모델 응답에 키나 내부 경로가 섞여
    #    나올 수 있고, 사용자에게 쓸모도 없다 — 보이는 것은 「실패」라는 상태뿐이다


class HistoryResponse(Schema):
    items: list[FittingResponse]
    counts: dict[str, int]       # 뱃지용. **거르기와 무관하게 항상 전체를 센다**


class FittingRequest(Schema):
    garment_id: uuid.UUID


class CompareRequest(Schema):
    garment_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_COMPARE)


async def _body_of(user: User, db: AsyncSession) -> Body:
    """프로필을 계산용 `Body` 로. 프로필 자체가 없을 때만 끊는다.

    ⚠️ **빈 치수는 A4 가 채운다** — 키·몸무게·성별만 넣은 사용자도 리포트를 받는다
       (PRD 7.2). 실측이 있으면 그 값이 이기고, 어디까지가 추정인지는 `measured` 가
       들고 가서 응답의 `confidence` 배지가 된다.
    """
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise AppError("PROFILE_NOT_FOUND", "프로필을 먼저 입력해 주세요", 404)
    값 = resolved_measurements(profile)
    return Body(
        chest=값["chest"],
        shoulder=값["shoulder"],
        waist=값["waist"],
        arm=값["arm"],
        # ⚠️ **채워진 값이 아니라 「직접 넣은 값」만 센다.** 여기에 추정을 넣으면
        #    추정 리포트가 「실측」 배지를 달고 나간다
        measured=frozenset(n for n in MEASUREMENTS if getattr(profile, n) is not None),
        preferred_grade=profile.preferred_grade,
        # A3(기장 판정)용. 총장이 몸의 어디까지 오는지는 **키**가 정한다 —
        # 성별은 밴드 폭에 비해 영향이 작지만(0.9cm 이내) A4 와 같은 처리로 맞춘다
        height=profile.height,
        gender=profile.gender,
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


def _view(
    fitting: Fitting, garment: Garment, job_status: str | None, urls: dict[str, str] | None = None
) -> FittingResponse:
    urls = urls or {}
    옷 = GarmentBrief.model_validate(garment)
    옷.photo_url = urls.get(garment.photo_path or "")
    return FittingResponse(
        id=fitting.id,
        # 잡이 없다 = 사진 없이 만든 리포트다. 없음 자체가 상태다
        status=job_status or REPORT_ONLY,
        garment=옷,
        report=FitReport.model_validate(fitting.report),
        image_path=fitting.image_path,
        image_url=urls.get(fitting.image_path or ""),
        created_at=fitting.created_at,
    )


async def _urls(*쌍: tuple[Fitting, Garment]) -> dict[str, str]:
    """목록 한 줄에 한 번씩 서명하면 그게 곧 지연이다 — 한 번에 물어본다."""
    return await storage.signed_urls(
        [k for f, g in 쌍 for k in (f.image_path, g.photo_path)]
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
            return _view(fitting, garment, job_status, await _urls((fitting, garment)))
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
    urls = await _urls(*[(f, g) for f, g, _ in rows])
    보이는것 = [_view(f, g, s, urls) for f, g, s in rows]
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

    전신 사진과 의류 사진이 **둘 다 있으면** 착용 이미지 잡을 큐에 넣는다 (D4).
    생성은 2분쯤 걸리므로(D0 실측 115초) 여기서 기다리지 않는다 — 상태는
    `GET /fittings/{id}` 로 확인한다.
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
    await db.commit()

    # ⚠️ **사진이 둘 다 있어야 큐에 넣는다.** 없으면 만들 그림이 없고, 없는 것을
    #    「대기」로 두면 영원히 안 끝나는 잡이 목록에 남는다 (계약 3). 리포트는 그대로 나간다
    profile = await db.get(Profile, user.id)
    큐에 = bool(profile and profile.photo_path and garment.photo_path)
    if 큐에:
        db.add(ImageJob(fitting_id=fitting.id))
        await db.commit()
    return _view(fitting, garment, "대기" if 큐에 else None)


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
    fitting, garment, job_status = row
    return _view(fitting, garment, job_status, await _urls((fitting, garment)))

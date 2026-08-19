"""B3 · 의류 등록 API

**한 행이 한 사이즈다.** 같은 옷의 M·L 은 두 번 등록하고, F-10 이 그 두 행을
나란히 놓는다 — 사이즈들을 묶는 테이블은 두지 않았다 (db/models.py).

⚠️ **사진 경로는 여기서 받지 않는다.** 등록은 치수만 받고, 사진은 업로드
   엔드포인트(`PUT /photos/garments/{id}`)가 붙인다 — 경로를 요청으로 받으면
   남의 사진을 가리키는 행을 만들 수 있다 (api/photos.py).
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import current_user
from core.schema import Schema
from db.models import Garment, User
from db.session import get_session
from fit.grade import STRETCH_RELIEF
from images import storage

router = APIRouter(prefix="/garments", tags=["garments"])

# CLAUDE.md 1절 확정 상수 — 상의 5종만
GARMENT_KINDS = ("티셔츠", "셔츠", "니트", "후디", "맨투맨")

# 신축성 문구는 fit.grade 가 유일한 출처다. 여기서 새로 타이핑하면
# 「보통」 같은 그럴듯한 값이 통과하고 보정이 조용히 0 이 된다
STRETCH_LEVELS = tuple(STRETCH_RELIEF)

Cm = Annotated[float, Field(gt=0, le=300)]
OptionalCm = Annotated[float | None, Field(default=None, gt=0, le=300)]


class GarmentRequest(Schema):
    kind: Literal[GARMENT_KINDS]
    size_name: str = Field(min_length=1, max_length=16)   # "M" · "95" · "FREE" — 자유 문자열

    # 필수 치수
    shoulder: Cm
    chest_width: Cm
    length: Cm

    # 선택 치수
    sleeve: OptionalCm
    waist_width: OptionalCm
    stretch: Literal[STRETCH_LEVELS] | None = None


class GarmentResponse(Schema):
    id: uuid.UUID
    kind: str
    size_name: str
    shoulder: float
    chest_width: float
    length: float
    sleeve: float | None
    waist_width: float | None
    stretch: str | None
    photo_path: str | None
    photo_url: str | None = None      # 비공개 버킷이라 조회 때마다 새로 서명한다


def _view(g: Garment, urls: dict[str, str]) -> GarmentResponse:
    r = GarmentResponse.model_validate(g)
    r.photo_url = urls.get(g.photo_path or "")
    return r


@router.post("", status_code=status.HTTP_201_CREATED)
async def register(
    body: GarmentRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> GarmentResponse:
    garment = Garment(user_id=user.id, **body.model_dump())
    db.add(garment)
    await db.commit()
    return _view(garment, {})       # 갓 만든 행에는 사진이 없다


@router.get("")
async def mine(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> list[GarmentResponse]:
    rows = list(
        await db.scalars(
            select(Garment).where(Garment.user_id == user.id).order_by(Garment.created_at.desc())
        )
    )
    # 한 줄에 한 번씩 서명하면 그게 곧 지연이다 — 한 번에 물어본다
    urls = await storage.signed_urls([g.photo_path for g in rows])
    return [_view(g, urls) for g in rows]

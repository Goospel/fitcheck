"""B3 · 의류 등록 API

**한 행이 한 사이즈다.** 같은 옷의 M·L 은 두 번 등록하고, F-10 이 그 두 행을
나란히 놓는다 — 사이즈들을 묶는 테이블은 두지 않았다 (db/models.py).

⚠️ 사진 업로드(D1)는 아직 없다. `photoPath` 는 **받아만 두고** 여기서 만들지
   않는다 — 업로드가 생기면 그 함수를 호출해 받은 경로를 그대로 넣는다.
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

    photo_path: str | None = Field(default=None, max_length=512)


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


@router.post("", status_code=status.HTTP_201_CREATED)
async def register(
    body: GarmentRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> GarmentResponse:
    garment = Garment(user_id=user.id, **body.model_dump())
    db.add(garment)
    await db.commit()
    return GarmentResponse.model_validate(garment)


@router.get("")
async def mine(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> list[GarmentResponse]:
    rows = await db.scalars(
        select(Garment).where(Garment.user_id == user.id).order_by(Garment.created_at.desc())
    )
    return [GarmentResponse.model_validate(g) for g in rows]

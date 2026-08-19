"""D1 · 사진 업로드 — 전신 사진 · 의류 사진

두 종류를 한 라우터에 둔다. 하는 일이 **완전히 같기 때문이다** — 받아서 검증(D2)하고
저장(`images/storage.py`)한 뒤 경로를 행에 적는다. 다른 것은 어느 행에 적느냐뿐이다.

⚠️ **경로를 클라이언트에게서 받지 않는다.** 받으면 남의 전신 사진 경로를 자기 행에
   넣을 수 있고, 조회할 때 서명 URL 이 그대로 발급된다. 경로는 사용자 id 로 시작하게
   서버가 만든다 (`images.storage.photo_key`).
"""

import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import current_user
from core.errors import AppError
from core.schema import Schema
from db.models import Garment, Profile, User
from db.session import get_session
from images import storage
from images.validate import normalize_photo

router = APIRouter(prefix="/photos", tags=["photos"])

# 업로드 상한. **PRD 확정 상수가 아니라 운영 값이다** — 폰 사진은 넉넉히 들어가고,
# 이보다 크면 사진이 아니라 사고다
MAX_BYTES = 10 * 1024 * 1024
_CHUNK = 1 << 20


class PhotoResponse(Schema):
    photo_path: str
    photo_url: str | None      # 비공개 버킷이라 이것 없이는 방금 올린 사진도 못 그린다


async def _읽기(file: UploadFile) -> bytes:
    """상한을 넘기면 **다 받기 전에** 끊는다.

    `await file.read()` 한 방이면 짧지만, 그 사이 500MB 가 디스크와 메모리를 지난 뒤에야
    거절하게 된다. 신뢰 경계라 여기서는 짧은 쪽을 고르지 않는다.
    """
    덩어리, 누계 = [], 0
    while 조각 := await file.read(_CHUNK):
        누계 += len(조각)
        if 누계 > MAX_BYTES:
            raise AppError(
                "PHOTO_TOO_LARGE", f"사진은 {MAX_BYTES // (1 << 20)}MB 이하로 올려 주세요", 413
            )
        덩어리.append(조각)
    return b"".join(덩어리)


async def _저장(행, file: UploadFile, user_id: uuid.UUID, garment_id=None) -> str:
    """검증 → 업로드 → 행에 경로 기록. **검증이 먼저다** — 거부할 사진을 먼저 올리면
    아무도 안 읽는 파일이 저장소에 쌓인다."""
    data, fmt = normalize_photo(await _읽기(file))
    key = storage.photo_key(user_id, fmt, garment_id)
    await storage.upload(key, data, fmt)

    옛것, 행.photo_path = 행.photo_path, key
    if 옛것 and 옛것 != key:
        # 형식이 바뀌면 확장자가 달라 키도 갈린다. 안 지우면 옛 파일이 그대로 남는다
        await storage.remove([옛것])
    return key


async def _응답(key: str) -> PhotoResponse:
    return PhotoResponse(photo_path=key, photo_url=(await storage.signed_urls([key])).get(key))


@router.put("/profile")
async def profile_photo(
    file: UploadFile,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> PhotoResponse:
    """전신 사진. 프로필이 있어야 붙일 자리가 있다."""
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise AppError("PROFILE_NOT_FOUND", "프로필을 먼저 입력해 주세요", 404)
    key = await _저장(profile, file, user.id)
    await db.commit()
    return await _응답(key)


@router.put("/garments/{garment_id}")
async def garment_photo(
    garment_id: uuid.UUID,
    file: UploadFile,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> PhotoResponse:
    """의류 제품컷. **남의 의류는 「없다」로 답한다** — 존재 여부를 흘리지 않는다."""
    garment = await db.scalar(
        select(Garment).where(Garment.id == garment_id, Garment.user_id == user.id)
    )
    if garment is None:
        raise AppError("GARMENT_NOT_FOUND", "등록된 의류를 찾을 수 없습니다", 404)
    key = await _저장(garment, file, user.id, garment_id)
    await db.commit()
    return await _응답(key)

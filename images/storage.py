"""D1 · 사진 저장 — Supabase Storage

⚠️ **버킷은 비공개다. 공개 URL 을 만들지 않는다** (CLAUDE.md 6절). 전신 사진이라
   주소만 알면 누구나 보는 상태가 되면 안 된다 — 읽기는 유효기간 있는 서명 URL 로만
   나간다.

⚠️ **경로는 서버가 만든다** (`photo_key`). 클라이언트가 경로를 넘길 수 있으면
   남의 사진을 가리키는 행을 만들 수 있고, 서명 URL 이 그대로 발급된다.

버킷은 처음 한 번만 만들면 된다 (`uv run python -m images.storage`).
"""

import asyncio
import uuid
from functools import lru_cache

from supabase import ASupabaseStorageClient

from core.config import settings
from core.errors import AppError
from images.validate import ALLOWED_FORMATS

BUCKET = "photos"

# 서명 URL 유효기간(초). **PRD 확정 상수가 아니라 운영 값이다** — 화면 한 번 보기에
# 넉넉하고, 주소가 새어 나가도 한 시간을 못 넘긴다
SIGNED_URL_TTL = 3600

# 한 번에 걷어 낼 수 있는 파일 수. Storage list 의 기본값이 100 이라 명시한다
_PAGE = 1000

_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

# 형식이 늘었는데 매핑을 빠뜨리면 **그 형식만 업로드에서 터진다.** 임포트 때 잡는다
assert set(_EXT) == set(ALLOWED_FORMATS), "지원 형식과 확장자 매핑이 어긋났다"


@lru_cache(maxsize=1)
def _client() -> ASupabaseStorageClient:
    """DB 엔진과 같은 약속 — 설정이 없어도 앱은 뜨고, 실제로 쓸 때 503 이 난다."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise AppError("STORAGE_NOT_CONFIGURED", "서버 설정이 아직 준비되지 않았습니다", 503)
    키 = settings.supabase_service_key
    return ASupabaseStorageClient(
        f"{settings.supabase_url}/storage/v1/",   # 슬래시가 없으면 SDK 가 경고한다
        {"apikey": 키, "Authorization": f"Bearer {키}"},
    )


def photo_key(user_id: uuid.UUID, fmt: str, garment_id: uuid.UUID | None = None) -> str:
    """저장 경로. 사용자 폴더 **바로 아래에 평평하게** 둔다.

    한 단계로 두는 이유 — 계정을 지울 때 `list` 한 번으로 그 사람의 파일이 전부
    걷힌다. 폴더를 더 파면 재귀 순회가 필요해지고, 빠뜨린 가지에 전신 사진이 남는다.

    확장자를 키에 박는 이유 — 다시 받을 때 content-type 을 추측하지 않는다.
    """
    이름 = f"garment-{garment_id}" if garment_id else "profile"
    return f"{user_id}/{이름}.{_EXT[fmt]}"


async def upload(key: str, data: bytes, fmt: str) -> None:
    """같은 키면 덮어쓴다 — 사진을 다시 올리는 것이 새 파일을 만드는 일이 아니다.

    ⚠️ **`cacheControl` 을 0 으로 준다.** 기본값은 3600 이라 CDN 이 한 시간 들고 있고,
       그러면 파일을 지운 뒤에도 **이미 발급된 서명 URL 로 캐시본이 계속 나온다**
       (실측: 계정을 지웠는데 옛 URL 이 200 을 돌려줬다). 전신 사진이라 「계정을
       지우면 사라진다」가 한 시간 뒤에 참이 되면 안 된다. 우리 규모에서 매번
       원본을 읽는 비용은 사람당 사진 몇 장이라 없는 것과 같다.
    """
    await _client().from_(BUCKET).upload(
        key,
        data,
        {"content-type": f"image/{fmt.lower()}", "upsert": "true", "cacheControl": "0"},
    )


async def signed_urls(keys) -> dict[str, str]:
    """경로 → 서명 URL. **없는 경로는 결과에서 빠진다.**

    한 번에 물어본다 — 목록 화면에서 한 줄에 한 번씩 왕복하면 그게 곧 지연이다.
    """
    쓸것 = [k for k in dict.fromkeys(keys) if k]
    if not 쓸것:
        return {}          # 사진이 하나도 없으면 네트워크를 아예 안 탄다
    rows = await _client().from_(BUCKET).create_signed_urls(쓸것, SIGNED_URL_TTL)
    return {r["path"]: r["signedUrl"] for r in rows if r.get("signedUrl")}


async def remove(keys: list[str]) -> None:
    if keys:
        await _client().from_(BUCKET).remove(keys)


async def remove_user_photos(user_id: uuid.UUID) -> None:
    """그 사람의 파일을 전부 지운다. 계정 삭제에서 부른다.

    ⚠️ **한 페이지만 지우고 끝내지 않는다.** 의류를 100벌 넘게 등록한 계정에서
       뒷장이 남으면 전신 사진이 그대로 남는다.
    """
    bucket = _client().from_(BUCKET)
    while 파일들 := await bucket.list(str(user_id), {"limit": _PAGE}):
        await bucket.remove([f"{user_id}/{f['name']}" for f in 파일들])


async def create_bucket() -> None:
    """처음 한 번. `uv run python -m images.storage`

    ⚠️ `public=False` 다. 공개로 만들면 서명 URL 을 쓰는 의미가 없어진다.
    """
    try:
        await _client().create_bucket(BUCKET, options={"public": False})
        print(f"버킷 '{BUCKET}' 생성 완료 (비공개)")
    except Exception as e:                       # 이미 있으면 그대로 둔다
        print(f"버킷 '{BUCKET}' — {e}")


if __name__ == "__main__":
    asyncio.run(create_bucket())

"""D4 · 이미지 생성 모델 실호출 — CLAUDE.md 2절 "images/ 안 한 곳에서만"의 그 한 곳

D0 스파이크(plan.md)에서 실측한 대로 간다: `openai` SDK 를 넣지 않고 httpx
multipart 로 직접 붙는다. 엔드포인트가 둘뿐이고, 재시도는 SDK가 아니라
`image_job.attempts`(jobs/worker.py)로 우리가 관리하므로 SDK 이점이 없다.
"""

import base64

import httpx

from core.config import settings
from core.errors import AppError

_ENDPOINT = "https://api.openai.com/v1/images/edits"

# D0 실측 — gpt-image-2 는 가로·세로가 둘 다 16의 배수여야 한다. 세로 인물사진이라 세로로 간다
_SIZE = "1024x1536"

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


async def generate_tryon(
    prompt: str, person: tuple[bytes, str], garment: tuple[bytes, str]
) -> bytes:
    """인물 사진 + 제품컷 → 착용 이미지.

    `person` · `garment` 는 (바이트, mime 타입) 쌍이다 — `images.storage.mime_of` 로 만든다.
    순서가 중요하다: **인물 먼저, 제품컷 나중** (D0 에서 확인된 순서).

    ⚠️ **`input_fidelity` 를 못 쓴다** — gpt-image-2 는 400 `invalid_input_fidelity_model`
       로 거절한다 (D0). 얼굴·무늬 보존은 프롬프트 문장에만 의존한다.
    """
    if not settings.openai_api_key:
        raise AppError(
            "IMAGE_MODEL_NOT_CONFIGURED", "이미지 생성 설정이 아직 준비되지 않았습니다", 503
        )

    files = [
        ("image[]", ("person", person[0], person[1])),
        ("image[]", ("garment", garment[0], garment[1])),
    ]
    data = {
        "model": settings.image_model,
        "prompt": prompt,
        "quality": "high",
        "n": "1",
        "size": _SIZE,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(_ENDPOINT, headers=headers, data=data, files=files)

    if response.status_code != 200:
        # 본문에 원인이 있지만 사용자에게 그대로 보여주지 않는다 — job_id.error 에만 남는다
        raise AppError(
            "IMAGE_GENERATION_FAILED", f"이미지 생성에 실패했습니다 ({response.status_code})", 502
        )

    b64 = response.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)

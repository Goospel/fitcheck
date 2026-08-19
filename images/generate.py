"""D4 · 착용 이미지 생성 — 모델을 부르는 **유일한 곳** (CLAUDE.md 2절)

호출 모양은 D0 스파이크에서 실측으로 확정했다 (plan.md D0):

    POST /v1/images/edits · image[] 두 장(인물 먼저, 제품컷 나중) · quality=high

⚠️ **`input_fidelity` 를 못 쓴다.** `gpt-image-2` 가 400 `invalid_input_fidelity_model`
   로 거절한다 — 얼굴·무늬 보존을 파라미터로 올릴 수 없고 프롬프트에만 의존한다.
   그래도 D0 에서 얼굴·무늬·큰 글자가 다 보존되는 것을 눈으로 확인했다.

⚠️ 여기서 만든 문장·응답은 **사용자에게 노출되지 않는다.** 프롬프트는 영어고
   (CLAUDE.md 6절), 에러 본문에는 키나 내부 경로가 섞여 나올 수 있다.
"""

import base64

import httpx

from core.config import settings

ENDPOINT = "https://api.openai.com/v1/images/edits"

# 세로. 가로·세로가 **둘 다 16의 배수**여야 한다 (D0 에서 400 으로 확인한 제약)
SIZE = "1024x1536"


async def generate_image(person: bytes, garment: bytes, prompt: str) -> bytes:
    """인물 사진 + 의류 제품컷 → 갈아입은 사진 (PNG bytes).

    타임아웃은 **여기서 걸지 않는다** — 잡 하나의 상한은 워커가 관리한다
    (`jobs/worker.py`). 두 곳에서 걸면 어느 쪽이 이겼는지 알 수 없어진다.
    """
    async with httpx.AsyncClient(timeout=None) as c:
        r = await c.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files=[
                ("image[]", ("person.jpg", person, "image/jpeg")),
                ("image[]", ("garment.jpg", garment, "image/jpeg")),
            ],
            data={"model": settings.image_model, "prompt": prompt,
                  "size": SIZE, "quality": "high", "n": "1"},
        )
    if r.status_code != 200:
        # 본문을 그대로 올리지 않는다 — 잡의 error 컬럼에 남고, 거기 키가 섞이면 곤란하다
        raise RuntimeError(f"이미지 생성 실패 (HTTP {r.status_code})")
    return base64.b64decode(r.json()["data"][0]["b64_json"])

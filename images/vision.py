"""D2 · 전신 사진 비전 검증 — 자를 때의 이유가 낡았다 (2026-08-21)

plan.md 8절은 이 항목을 「각각 별도 비전 모델이 필요하고 6시간+」이라 잘랐다. 그때는
맞았지만 지금은 **이미 OpenAI 를 쓰고 있어** 호출 하나로 끝난다. 자른 판단이 틀렸던
게 아니라 **전제가 바뀐 것**이다.

무엇을 막는가 — 생성 한 장이 **2분 + 유료 API** 다. 제품컷을 전신 사진 자리에 올리면
지금은 2분을 기다린 끝에 이상한 그림을 받는다. 입구에서 걸러 그 2분을 아낀다.

⚠️ **애매하면 통과시킨다 (fail-open).** 업로드는 서비스의 입구다. 비전 모델이 흔들리거나
   API 가 죽었다고 입구를 막으면 막힌 사람에게 우회로가 없다. 해상도·포맷 검사
   (`images/validate.py`) 는 그대로 돌고, 최악은 「이상한 사진 → 이상한 결과」인데
   그건 다시 올리면 되돌아온다. 「사진을 아예 못 올린다」는 안 되돌아온다.

⚠️ **`VISION_CHECK=false` 로 즉시 끌 수 있다.** 시연 중에 오판이 나면 코드가 아니라
   환경변수로 끈다 — 새 실패 모드를 입구에 하나 더 놓는 값이다.

⚠️ **정면 판별은 넣지 않았다.** 자른 범위에 있었지만, 옆모습으로도 착용 이미지는
   멀쩡히 나온다. 막지 않을 판정을 계산하는 것은 돈과 지연만 늘린다.

⚠️ **의류 사진에는 걸지 않는다.** 제품컷에 사람이 없는 것이 정상이다.
"""

import base64
import json
import logging

import httpx

from core.config import settings
from core.errors import AppError

log = logging.getLogger(__name__)

ENDPOINT = "https://api.openai.com/v1/chat/completions"

# 스파이크 실측 2.6~4.7초 (scratchpad/d2_spike.py · 4/4 정답). 넘으면 통과시킨다 —
# 업로드를 20초 이상 붙잡는 것이 오판보다 나쁘다
TIMEOUT = 20.0

# 사용자에게 그대로 보이는 문장이다. **모델이 쓴 문장을 쓰지 않는다** — 매번 달라지고
# 영어가 섞여 나올 수 있다 (CLAUDE.md 6절: 사용자에게 보이는 문구는 한국어)
REJECTIONS = {
    "safe": "이 사진은 사용할 수 없습니다. 다른 사진을 올려 주세요",
    "person": "사진에서 사람을 찾지 못했습니다. 전신이 나온 사진을 올려 주세요",
    "full_body": "머리부터 발끝까지 나온 전신 사진이 필요합니다",
}

# 판정 순서 = 말할 순서. 사람이 없으면 전신 여부는 물어볼 것도 없다
_ORDER = ("safe", "person", "full_body")

_INSTRUCTION = (
    "You are validating a photo submitted as a full-body reference for a virtual "
    "try-on service. Answer ONLY with JSON matching this shape:\n"
    '{"person": bool, "full_body": bool, "safe": bool, "reason": "<short reason>"}\n\n'
    "person: exactly one human clearly visible (false for product-only photos).\n"
    "full_body: head through feet all visible.\n"
    "safe: false if nudity, violence, or otherwise inappropriate."
)


def verdict(payload: dict | None) -> str | None:
    """모델 응답 → 거부 사유 (통과면 None). **순수 함수다.**

    셋 중 하나라도 bool 이 아니면 **판정을 포기하고 통과시킨다.** 모델이 스키마를
    안 지킨 것과 「나쁜 사진이다」는 다르고, 둘을 섞으면 멀쩡한 사진이 거부된다.
    """
    if not isinstance(payload, dict):
        return None
    for 키 in _ORDER:
        값 = payload.get(키)
        if not isinstance(값, bool):
            return None
        if not 값:
            return REJECTIONS[키]
    return None


async def _ask(raw: bytes) -> dict | None:
    """비전 모델에 물어본다. 무슨 일이 나든 None 으로 떨어진다 (fail-open)."""
    b64 = base64.b64encode(raw).decode()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.vision_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": _INSTRUCTION},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ]}],
                    "response_format": {"type": "json_object"},
                },
            )
        if r.status_code != 200:
            # 본문을 그대로 남기지 않는다 — 키가 섞여 나올 수 있다 (images/generate.py 와 같은 이유)
            log.warning("비전 검증 호출 실패 (HTTP %s) — 통과시킨다", r.status_code)
            return None
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:      # noqa: BLE001 — 여기가 fail-open 경계다. 무엇이 터지든 통과
        log.warning("비전 검증을 건너뛴다: %s", type(e).__name__)
        return None


async def check_person_photo(raw: bytes) -> None:
    """전신 사진이 아니면 `AppError` 를 올린다. 판정을 못 하면 조용히 통과시킨다.

    ⚠️ **EXIF 를 편 뒤의 바이트를 넘긴다** (`normalize_photo` 의 결과). 원본을 넘기면
       눕혀 저장된 폰 사진이 모델 눈에도 누워 보여 「전신 아님」으로 오판된다.
    """
    if not settings.vision_check or not settings.openai_api_key:
        return
    응답 = await _ask(raw)
    사유 = verdict(응답)
    if 사유 is not None:
        # 모델이 쓴 reason 은 사용자에게 안 보내고 로그에만 남긴다 — 오판을 쫓을 단서다
        log.info("전신 사진 거부: %s (모델: %r)", 사유, (응답 or {}).get("reason"))
        raise AppError("PHOTO_UNUSABLE", 사유, 400)

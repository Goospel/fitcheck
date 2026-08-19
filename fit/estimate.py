"""A4 · 신체 치수 추정 — 키·몸무게·성별 → 어깨너비·가슴둘레·허리둘레·팔길이

실측을 안 넣은 사용자도 리포트를 받게 한다 (PRD 7.2). **실측이 있으면 그 값이
이기고 여기 값은 쓰이지 않는다** — 추정은 빈칸을 메우는 용도다.

⚠️ **여기 숫자는 지어낸 것이 아니다** (CLAUDE.md 1절). 아래 앵커는 국가기술표준원
   **제8차 한국인 인체치수조사(Size Korea)** 의 20~24세 평균이고, 2026-08-20 에
   sizekorea.kr 「인체 항목 검색」에서 직접 조회해 mm → cm 로 옮긴 값이다.
   표본은 항목당 남 789~798명 · 여 714~716명. 값을 고치려면 출처를 같이 바꾼다.

⚠️ **스케일 법칙은 가정이다.** 조사가 주는 것은 「평균과 분위수」지 「키 175 ·
   몸무게 70인 사람의 가슴둘레」가 아니다. 그래서 평균을 앵커로 놓고 두 가지
   물리적 성질로 늘린다.

     길이(어깨·팔) ∝ 키
     둘레(가슴·허리) ∝ √(몸무게 / 키)

   뒤엣것은 「몸의 평균 단면적 ≈ 부피/키 ∝ 몸무게/키, 둘레 ∝ √단면적」에서 온다.
   닮은꼴로 커지면(키 ×1.1, 몸무게 ×1.331) 둘레도 ×1.1 이 되는 성질을 만족한다.

   ⚠️ **허리는 이 가정이 가장 약한 자리다** — 살은 허리에 먼저 붙으므로 실제로는
   가슴보다 몸무게에 더 민감하다. 지수를 다르게 두려면 원시 데이터로 적합해야
   하는데 그 데이터가 없다. 지수를 눈대중으로 손대는 것이 더 나쁘므로 같은 식을 쓴다.

⚠️ **어깨너비의 정의가 옷과 정확히 같지는 않다.** 조사값은 등을 따라 두 어깨가쪽점
   사이를 잰 체표 거리고, 의류 어깨너비는 봉제선 사이 평면 거리다. 체표 쪽이 조금
   길다. 가슴이 등급을 정하고 어깨는 보조 지표라 여기까지만 맞춘다.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Anchor:
    """어떤 체형 하나를 통째로 고정한 점. 이 점을 지나도록 스케일한다."""

    height: float
    weight: float
    chest: float
    shoulder: float
    waist: float
    arm: float


@dataclass(frozen=True)
class Estimated:
    """`fit.report.Body` 의 치수 4종과 이름을 맞춘다 — 그대로 넘겨 쓰라고."""

    chest: float
    shoulder: float
    waist: float
    arm: float


# 제8차 한국인 인체치수조사 · 20~24세 평균 (cm). **출처 없이 고치지 않는다.**
ANCHORS: dict[str, Anchor] = {
    "남성": Anchor(height=174.99, weight=72.68, chest=101.04, shoulder=40.01, waist=82.06, arm=59.06),
    "여성": Anchor(height=161.79, weight=55.31, chest=88.17, shoulder=34.70, waist=72.62, arm=54.10),
}


def _from(anchor: Anchor, height: int, weight: int) -> Estimated:
    키비 = height / anchor.height
    # 둘레는 단면적에서 온다 — 몸무게만 보면 키 큰 사람이 늘 뚱뚱해진다
    체형비 = math.sqrt((weight / anchor.weight) / 키비)
    return Estimated(
        chest=round(anchor.chest * 체형비, 1),
        shoulder=round(anchor.shoulder * 키비, 1),
        waist=round(anchor.waist * 체형비, 1),
        arm=round(anchor.arm * 키비, 1),
    )


def estimate_body(height: int, weight: int, gender: str | None) -> Estimated:
    """키·몸무게·성별로 치수 4종을 추정한다. **입력 범위 검증은 프로필이 이미 했다.**

    성별을 밝히지 않았으면 **두 추정의 중간**을 쓴다 — 정보가 없을 때 한쪽으로
    기울이지 않는다. 모르는 문자열이 와도 같은 처리다(옛 프로필이 살아 있을 수 있다).
    """
    anchor = ANCHORS.get(gender or "")
    if anchor is not None:
        return _from(anchor, height, weight)

    남, 여 = (_from(a, height, weight) for a in ANCHORS.values())
    return Estimated(
        chest=round((남.chest + 여.chest) / 2, 1),
        shoulder=round((남.shoulder + 여.shoulder) / 2, 1),
        waist=round((남.waist + 여.waist) / 2, 1),
        arm=round((남.arm + 여.arm) / 2, 1),
    )

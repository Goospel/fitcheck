"""A1 · 여유량 계산 — CLAUDE.md 1절 「여유량 계산식」

DB·네트워크·시간에 의존하지 않는 순수 함수다 (CLAUDE.md 6절). 치수는 전부 cm.

⚠️ **결과를 소수 한 자리로 맞춘다.** 계산식은 그대로고 정밀도만 못 박는 것이다.
   안 그러면 이진 부동소수점 찌꺼기가 **그대로 화면에 나간다** — 배포 서버에서
   실제로 `54.0 × 2 − 99.2 = 8.799999999999997` 이 응답에 실렸다 (2026-08-20).
   계약 2 의 `chestEase` 는 프론트가 그대로 그리는 값이라 여기서 정리해야 한다.

⚠️ **A4 가 만든 문제는 아니지만 A4 가 드러냈다.** 실측만 쓰던 때는 92.0 · 51.0 처럼
   0.0 으로 끝나는 값이라 우연히 딱 떨어졌다. 추정값은 1자리 소수라 항상 걸린다.

⚠️ **등급도 이 값으로 판정된다** (`fit.report` 가 여기 결과를 그대로 넘긴다).
   그래야 「여유 6.0cm · 슬림핏」 같은 자기모순이 화면에 안 뜬다. 임계값
   0/6/14/24 는 그대로다 — 비교에 넣는 값의 정밀도만 정한 것이다.
"""

# 옷도 몸도 0.1cm 단위로 잰다. 그보다 잘게 말해 봐야 줄자가 못 따라온다
_자리 = 1


def chest_ease(garment_chest_width: float, user_chest: float) -> float:
    """가슴 여유 = (의류 가슴단면 × 2) − 사용자 가슴둘레"""
    return round(garment_chest_width * 2 - user_chest, _자리)


def waist_ease(
    garment_waist_width: float | None, user_waist: float | None
) -> float | None:
    """허리 여유 = (의류 허리단면 × 2) − 사용자 허리둘레

    의류 허리단면도 사용자 허리둘레도 선택 입력이다. 하나라도 없으면 계산하지 않고
    None 을 돌려준다 — 리포트에서 이 줄이 통째로 빠진다. 여유량 0(딱 맞음)과
    None(모름)은 다른 값이므로 falsy 로 뭉개지 않는다.
    """
    if garment_waist_width is None or user_waist is None:
        return None
    return round(garment_waist_width * 2 - user_waist, _자리)


def shoulder_diff(garment_shoulder: float, user_shoulder: float) -> float:
    """어깨 차이 = 의류 어깨너비 − 사용자 어깨너비"""
    return round(garment_shoulder - user_shoulder, _자리)


def sleeve_diff(garment_sleeve: float | None, user_arm: float | None) -> float | None:
    """소매 길이 차 = 의류 소매길이 − 사용자 팔길이

    소매길이는 B3에서 선택 입력이다. 없으면 계산하지 않는다.
    """
    if garment_sleeve is None or user_arm is None:
        return None
    return round(garment_sleeve - user_arm, _자리)

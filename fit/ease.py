"""A1 · 여유량 계산 — CLAUDE.md 1절 「여유량 계산식」

DB·네트워크·시간에 의존하지 않는 순수 함수다 (CLAUDE.md 6절). 치수는 전부 cm.
"""


def chest_ease(garment_chest_width: float, user_chest: float) -> float:
    """가슴 여유 = (의류 가슴단면 × 2) − 사용자 가슴둘레"""
    return garment_chest_width * 2 - user_chest


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
    return garment_waist_width * 2 - user_waist


def shoulder_diff(garment_shoulder: float, user_shoulder: float) -> float:
    """어깨 차이 = 의류 어깨너비 − 사용자 어깨너비"""
    return garment_shoulder - user_shoulder


def sleeve_diff(garment_sleeve: float | None, user_arm: float | None) -> float | None:
    """소매 길이 차 = 의류 소매길이 − 사용자 팔길이

    소매길이는 B3에서 선택 입력이다. 없으면 계산하지 않는다.
    """
    if garment_sleeve is None or user_arm is None:
        return None
    return garment_sleeve - user_arm

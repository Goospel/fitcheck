"""A2 · 핏 등급 판정 — CLAUDE.md 1절 「핏 등급 임계값」

            0        6        14       24
      ------|--------|--------|--------|------>
      타이트  슬림    레귤러   세미오버   오버

⚠️ 이 값을 임의로 조정하지 않는다. 어긋나면 핏 리포트·이미지 프롬프트·사이즈 비교
화면이 한꺼번에 깨진다. 바꿔야 하면 팀 3명 다 동의해야 한다.
"""

# (하한, 등급) — 하한 포함, 상한 미포함. 큰 쪽부터 본다.
THRESHOLDS: tuple[tuple[int, str], ...] = (
    (24, "오버핏"),
    (14, "세미오버핏"),
    (6, "레귤러핏"),
    (0, "슬림핏"),
)

# 어느 구간에도 안 걸리면(= 여유량이 최저 하한 미만) 여기로 떨어진다.
# ⚠️ PRD 6.2.2 의 등급명은 「타이트핏」이 아니라 **「너무 작음」**이다 — 핏이 아니라 경고다
TOO_SMALL = "너무 작음"

# 타이트 → 오버 순서. 게이지 단계와 선호 핏 비교가 이 순서에 의존한다.
# THRESHOLDS 에서 파생시켜 문구가 한 곳에만 있게 한다.
GRADE_ORDER: tuple[str, ...] = (TOO_SMALL, *(grade for _, grade in reversed(THRESHOLDS)))

# 사용자가 **선호 핏으로 고를 수 있는** 것 (PRD 7.2 — 슬림/레귤러/세미오버/오버).
# 「너무 작음」은 취향이 아니라 경고라 선택지에서 뺀다
PREFERRED_GRADES: tuple[str, ...] = GRADE_ORDER[1:]

# 신축성이 있으면 같은 여유량이 더 헐렁하게 입힌다 → 각 구간 하한을 낮춘다
STRETCH_RELIEF: dict[str, int] = {"좋음": 6, "약간": 4, "없음": 0}


def fit_grade(chest_ease: float, stretch: str | None = None) -> str:
    """가슴 여유량(cm)과 신축성으로 핏 등급을 낸다.

    신축성이 미입력이거나 목록에 없는 값이면 "없음"으로 간주한다 — 보정을 주지 않는
    쪽이 더 타이트하게 판정되고, 큰 옷을 사게 하는 편이 작은 옷보다 낫다.
    """
    relief = STRETCH_RELIEF.get(stretch, 0)
    for floor, grade in THRESHOLDS:
        if chest_ease >= floor - relief:
            return grade
    return TOO_SMALL

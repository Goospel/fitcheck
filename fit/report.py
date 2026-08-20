"""A5 · 리포트 조립 — 계약 2

A1(여유량)과 A2(등급)을 묶어 **프론트와 BE-3의 D3가 함께 읽는 한 덩어리**로 만든다.
DB·네트워크·시간에 의존하지 않는 순수 함수다 (CLAUDE.md 6절).

⚠️ **기장은 A3 가 채운다** (2026-08-20 · Q1 종결). 판정에 사용자 키가 필요해서
   `Body` 에 `height`·`gender` 가 붙었다 — 둘 다 선택이고, 키가 없으면 예전처럼 None 이다.

⚠️ **소매는 아직 None 이다** (docs/open-questions.md Q2). 「손목 = 차이 0」은 데이터가
   답하지만 밴드 폭은 합의 사항이라 인체 데이터로 안 풀린다. 정해지면 여기서 채운다.
"""

from dataclasses import dataclass, field

from core.schema import Schema
from fit.ease import chest_ease, shoulder_diff, sleeve_diff, waist_ease
from fit.grade import GRADE_ORDER, fit_grade
from fit.length import LENGTH_LABELS, length_label

# 소매 3단계 문구 — PRD 6.2.3 확정. 판정 기준(경계 숫자)은 아직 없다 (Q2).
# ⚠️ 기장 문구 LENGTH_LABELS 는 **판정 로직 옆에 있으라고** fit/length.py 로 옮겼다.
#    여기서 재수출하므로 `from fit.report import LENGTH_LABELS` 는 그대로 쓸 수 있다
#    (images/prompt.py 가 그렇게 읽는다).
SLEEVE_LABELS: tuple[str, ...] = ("손목 위", "손목", "손등 일부 덮음")

# 신뢰도 배지 기준 — 이 셋을 전부 직접 입력했을 때만 "실측"이다.
# 팔길이는 등급 판정에 안 쓰이므로 배지에도 넣지 않는다.
CONFIDENCE_FIELDS = frozenset({"chest", "shoulder", "waist"})


@dataclass(frozen=True)
class Body:
    """사용자 신체 치수 (cm).

    `measured` 에 든 항목만 실측이고 나머지는 A4 추정값이다 (CLAUDE.md 6절 — 값과
    출처를 같이 들고 다닌다). 허리·팔은 선택 입력이라 None 일 수 있다.
    """

    chest: float
    shoulder: float
    waist: float | None = None
    arm: float | None = None
    measured: frozenset[str] = field(default_factory=frozenset)
    preferred_grade: str | None = None
    # A3(기장 판정)용. 경계는 골격에서 나오므로 **키만** 쓴다 — 몸무게는 안 본다.
    # 프로필에선 둘 다 필수지만 여기선 선택이다 — 키가 없으면 lengthLabel 이 None 이다
    height: int | None = None
    gender: str | None = None


@dataclass(frozen=True)
class Garment:
    """의류 실측 치수 (cm). 필수·선택 구분은 plan.md B3를 따른다."""

    chest_width: float           # 가슴단면
    shoulder: float              # 어깨너비
    length: float                # 총장 — A3(기장 판정)가 풀리면 쓰인다
    waist_width: float | None = None
    sleeve: float | None = None
    stretch: str | None = None   # 좋음 / 약간 / 없음 · 미입력은 "없음" 취급


class FitReport(Schema):
    """계약 2. 필드 이름을 바꾸면 D3와 프론트가 같이 깨진다.

    선택 값이 없어도 **키는 항상 남는다** — 프론트가 키 존재 여부로 분기하지 않게.
    """

    fit_grade: str
    gauge_level: int                  # 1(타이트) ~ 5(오버)
    chest_ease: float
    waist_ease: float | None
    shoulder_diff: float
    sleeve_diff: float | None
    length_label: str | None          # Q1 확정 전까지 None
    sleeve_label: str | None          # Q2 확정 전까지 None
    confidence: str                   # "실측" | "추정"
    preferred_grade: str | None
    grade_distance: int | None        # 선호 대비 단계 차. 양수면 실제가 더 헐렁
    show_preference_cta: bool         # 선호 핏 미설정 → 설정 유도


def build_report(body: Body, garment: Garment) -> FitReport:
    """프로필과 의류 치수로 핏 리포트를 만든다.

    선호 핏이 없거나 등급 목록에 없는 값이면 비교를 통째로 생략하고 CTA를 올린다
    (plan.md A5). 프로필에 옛 문구가 남아 있어도 500을 내지 않는다.
    """
    chest = chest_ease(garment.chest_width, body.chest)
    grade = fit_grade(chest, garment.stretch)

    preferred = body.preferred_grade if body.preferred_grade in GRADE_ORDER else None
    distance = (
        GRADE_ORDER.index(grade) - GRADE_ORDER.index(preferred)
        if preferred is not None
        else None
    )

    return FitReport(
        fit_grade=grade,
        gauge_level=GRADE_ORDER.index(grade) + 1,
        chest_ease=chest,
        waist_ease=waist_ease(garment.waist_width, body.waist),
        shoulder_diff=shoulder_diff(garment.shoulder, body.shoulder),
        sleeve_diff=sleeve_diff(garment.sleeve, body.arm),
        length_label=length_label(garment.length, body.height, body.gender),
        sleeve_label=None,   # Q2(소매 밴드 폭) 미확정 — 지어내지 않는다
        confidence="실측" if CONFIDENCE_FIELDS <= body.measured else "추정",
        preferred_grade=preferred,
        grade_distance=distance,
        show_preference_cta=preferred is None,
    )

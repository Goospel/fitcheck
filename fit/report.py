"""A5 · 리포트 조립 — 계약 2

A1(여유량)과 A2(등급)을 묶어 **프론트와 BE-3의 D3가 함께 읽는 한 덩어리**로 만든다.
DB·네트워크·시간에 의존하지 않는 순수 함수다 (CLAUDE.md 6절).

⚠️ 기장·소매 문구는 판정 기준이 미확정이라 항상 None 이다
   (docs/open-questions.md Q1 · Q2). A3가 풀리면 여기서 채운다.
"""

from dataclasses import dataclass, field

from core.schema import Schema
from fit.ease import chest_ease, shoulder_diff, sleeve_diff, waist_ease
from fit.grade import GRADE_ORDER, fit_grade

# 기장 5단계 · 소매 3단계 문구 — PRD 6.2.3 확정. **여기가 유일한 출처다.**
# 판정 기준(경계 숫자)은 아직 없지만(Q1 · Q2) 문구는 확정이라 미리 못 박아 둔다.
# A3(랜드마크 판정)와 D3(프롬프트 변환)가 둘 다 이 목록을 봐야 한다.
LENGTH_LABELS: tuple[str, ...] = (
    "허리 위로 올라오는 크롭 기장",
    "허리에 딱 떨어지는 기장",
    "골반에 걸치는 기본 기장",
    "엉덩이를 반쯤 덮는 기장",
    "엉덩이를 완전히 덮는 롱 기장",
)

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
        length_label=None,   # Q1 미확정 — 지어내지 않는다
        sleeve_label=None,   # Q2 미확정
        confidence="실측" if CONFIDENCE_FIELDS <= body.measured else "추정",
        preferred_grade=preferred,
        grade_distance=distance,
        show_preference_cta=preferred is None,
    )

"""A3 · 기장 판정 — 경계 4개는 지어낸 값이 아니다 (Q1 종결 · 2026-08-20)

CLAUDE.md 1절의 기장 문구 5종은 **실제 인체 랜드마크를 그대로 부른다**. 그래서
「골반이 몇 cm인가」를 정할 필요가 없다 — 제8차 한국인 인체치수조사에 그 랜드마크의
바닥 기준 높이가 항목으로 그대로 있다.

    허리에 딱 떨어지는   → 허리높이
    골반에 걸치는        → 엉덩위높이/Top-hip높이
    엉덩이를 반쯤 덮는   → 엉덩이높이
    엉덩이를 완전히 덮는 → 볼기고랑높이/다리안쪽높이

높이는 전부 바닥 기준이라 총장과 비교하려면 뒤집는다.

    경계 = 목뒤높이 − 랜드마크높이        (목뒤에서 아래로 몇 cm)

⚠️ **하한 포함·상한 미포함** — 핏 등급 임계값(0/6/14/24)과 같은 규칙이다.

⚠️ **키로만 스케일한다.** 길이 랜드마크는 골격이라 A4 의 `키비` 를 그대로 쓴다.
   둘레에 쓰는 `체형비`(몸무게 반영)가 아니다 — 살이 쪄도 허리 위치는 안 내려간다.

──────────────────────────────────────────────────────────────────────
알고 써야 하는 근사 둘 — 둘 다 계산을 **길게** 만드는 쪽이다
──────────────────────────────────────────────────────────────────────

**① 총장은 평면 실측이고 랜드마크 높이는 수직 높이다.** 옷을 눕혀서 잰 총장은
   직선이지만, 입으면 등의 곡면을 타고 내려가 실제 도달점은 계산보다 **조금 위**다.
   보정치를 지어내지 않고 `DRAPE_ALLOWANCE = 0.0` 으로 두었다 — 실착 데이터가
   생기면 이 값 하나만 올리면 전체 경계가 같이 올라간다.

**② 총장의 기준점.** 국내 실측 표기는 보통 어깨 최고점(HPS)에서 잰다. HPS 는
   해부학적으로 **목옆점**이고, 목옆높이(남 147.68 · 여 135.72)와 목뒤높이의 차이는
   **0.67cm · 0.61cm** 다. 밴드 폭이 8~10cm 라 이 차이는 판정을 못 바꾼다.
   그래서 표본이 크고 직접측정인 **목뒤높이**(n=789/714, `-DM`)를 기준으로 잡았다.
   목옆높이는 `-SM`(n=446/443)이라 표본이 절반이다.
"""

from dataclasses import dataclass

from fit.estimate import ANCHORS

# 기장 5단계 문구 — PRD 6.2.3 확정. **여기가 유일한 출처다.**
# `fit.report` 가 그대로 재수출하므로 기존 `from fit.report import LENGTH_LABELS` 도 산다.
# 순서가 곧 짧은 것 → 긴 것이고, 아래 판정이 이 순서에 의존한다.
LENGTH_LABELS: tuple[str, ...] = (
    "허리 위로 올라오는 크롭 기장",
    "허리에 딱 떨어지는 기장",
    "골반에 걸치는 기본 기장",
    "엉덩이를 반쯤 덮는 기장",
    "엉덩이를 완전히 덮는 롱 기장",
)

# 옷도 몸도 0.1cm 단위다 (fit/ease.py 와 같은 정밀도)
_자리 = 1

# 평면 총장 → 착용 시 수직 낙차 보정 (cm). **실측 근거가 없어 0 이다.**
# 0 이 아닌 값을 넣으려면 실착 비교 데이터가 있어야 한다 — 지어내지 않는다
DRAPE_ALLOWANCE = 0.0


@dataclass(frozen=True)
class Landmarks:
    """바닥 기준 높이 (cm) — 값이 클수록 몸에서 위쪽이다"""

    nape: float        # 목뒤높이            S-STa-H-[FL01-NK03]-DM
    waist: float       # 허리높이            S-STa-H-[FL01-WS11]-DM
    top_hip: float     # 엉덩위높이/Top-hip  S-STa-H-[FL01-HP31]-SM
    hip: float         # 엉덩이높이          S-STa-H-[FL01-HP40]-DM
    gluteal: float     # 볼기고랑높이        S-STa-H-[FL01-UL01]-SM


# 제8차 한국인 인체치수조사 · 20~24세 평균 (cm). **출처 없이 고치지 않는다.**
# 조회: sizekorea.kr → 인체 항목 검색 → 8차 · 연령 20-24 · 성별. 항목 코드는 위 주석.
# 연령대는 A4 앵커(fit/estimate.py)와 같은 20~24세로 맞췄다 — 다르면 조용히 갈라진다.
LANDMARKS: dict[str, Landmarks] = {
    "남성": Landmarks(nape=148.35, waist=106.56, top_hip=96.79, hip=86.17, gluteal=77.90),
    "여성": Landmarks(nape=136.33, waist=98.42, top_hip=89.13, hip=79.10, gluteal=71.19),
}


def _bounds_of(성별: str, height: int) -> tuple[float, ...]:
    """한 성별의 경계 4개 — 앵커에서 재고 키 비율로 늘린다"""
    lm = LANDMARKS[성별]
    키비 = height / ANCHORS[성별].height
    return tuple(
        (lm.nape - 랜드마크) * 키비 + DRAPE_ALLOWANCE
        for 랜드마크 in (lm.waist, lm.top_hip, lm.hip, lm.gluteal)
    )


def length_bounds(height: int, gender: str | None) -> tuple[float, float, float, float]:
    """목뒤에서 각 랜드마크까지의 거리 4개 (cm, 짧은 것부터).

    성별을 안 밝히면 남녀 경계의 중간을 쓴다 — A4 추정기와 같은 처리다
    (`fit.estimate.estimate_body`). 목록에 없는 값도 같게 본다.
    """
    if gender in LANDMARKS:
        값 = _bounds_of(gender, height)
    else:
        남, 여 = (_bounds_of(g, height) for g in LANDMARKS)
        값 = tuple((m + f) / 2 for m, f in zip(남, 여))
    b1, b2, b3, b4 = (round(x, _자리) for x in 값)
    return b1, b2, b3, b4


def length_label(
    garment_length: float, height: int | None, gender: str | None
) -> str | None:
    """의류 총장으로 기장 문구를 고른다. 키를 모르면 판정하지 않는다.

    프로필에 키는 필수지만 `Body` 는 순수 자료구조라 비어 있을 수 있다. 그 경우
    그럴듯한 문구를 만들지 말고 None 을 낸다 — 계약상 `lengthLabel` 은 선택 필드다.
    """
    if height is None:
        return None
    # 하한 포함·상한 미포함. 긴 쪽부터 보면 첫 일치가 답이다
    경계 = length_bounds(height, gender)
    for 하한, 문구 in zip(reversed(경계), reversed(LENGTH_LABELS[1:])):
        if garment_length >= 하한:
            return 문구
    return LENGTH_LABELS[0]

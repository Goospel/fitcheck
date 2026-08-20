"""D3 · 프롬프트 변환 — 계산 결과를 이미지 생성 지시문으로 (PRD 6.3)

이미지 생성 AI 는 「가슴 여유 18cm」를 이해하지 못한다. 픽셀 패턴을 학습했을 뿐
센티미터를 모른다 (PRD 6.1). 그래서 **6.2 가 계산한 숫자를 말로 바꿔서** 넘긴다.

⚠️ **이 문장은 사용자에게 절대 노출되지 않는다** (CLAUDE.md 6절). 사용자가 화면에서
   보는 것은 한국어 핏 리포트뿐이고, 여기 있는 영어는 모델에게만 간다.

⚠️ 지시문의 **왼쪽 열(한국어 라벨)은 확정 목록에서만 온다** — `fit.grade.GRADE_ORDER`
   와 `fit.report.LENGTH_LABELS` · `SLEEVE_LABELS`. 여기서 문자열을 새로 타이핑하면
   목록이 바뀔 때 조용히 갈라진다. 아래 dict 의 키가 목록과 같은지는 테스트가 지킨다.
"""

from fit.grade import GRADE_ORDER
from fit.report import LENGTH_LABELS, SLEEVE_LABELS, FitReport

# 사진 두 장에 대한 요구 — PRD 6.3 「요구사항」 ①②
BASE_PROMPT = (
    "Photorealistic photo of the person from the reference image wearing the garment "
    "from the product image. "
    "Keep the person's face, hair and body proportions exactly as in the reference image. "
    "Keep the garment's design, color and pattern exactly as in the product image."
)

# ── 핏 등급 → 그림 지시 ────────────────────────────────────────────────
# PRD 6.3 이 준 예시는 「세미오버핏 → 약간 넉넉한 핏으로, 가슴에 여유가 있게」 한 줄이다.
# 나머지는 확정된 등급 문구를 같은 결로 옮긴 것 — 숫자가 아니라 묘사라 조정해도 안전하다.
GRADE_PROMPTS: dict[str, str] = {
    "너무 작음": "The top is clearly too small: it pulls tight across the chest with visible strain.",
    "슬림핏": "A slim fit that follows the body line closely, with little slack.",
    "레귤러핏": "A regular fit with moderate, comfortable ease through the chest.",
    "세미오버핏": "A slightly roomy fit with noticeable ease across the chest.",
    "오버핏": "A distinctly oversized fit with generous volume through the body.",
}

# ── 기장 → 그림 지시 ──────────────────────────────────────────────────
# ⚠️ A3(판정)가 아직 없어 `lengthLabel` 은 항상 None 이다 (Q1). 매핑은 미리 갖춰 두므로
#    A3 가 붙는 순간 이 파일은 손대지 않아도 문장이 늘어난다.
LENGTH_PROMPTS: dict[str, str] = {
    "허리 위로 올라오는 크롭 기장": "The hem sits above the waist, cropped.",
    "허리에 딱 떨어지는 기장": "The hem falls right at the waist.",
    "골반에 걸치는 기본 기장": "The hem rests on the hips.",
    "엉덩이를 반쯤 덮는 기장": "The hem covers half of the buttocks.",
    "엉덩이를 완전히 덮는 롱 기장": "The hem fully covers the buttocks, a long silhouette.",
}

# ── 소매 → 그림 지시 ──────────────────────────────────────────────────
SLEEVE_PROMPTS: dict[str, str] = {
    "손목 위": "The sleeves end above the wrist.",
    "손목": "The sleeves end at the wrist.",
    "손등 일부 덮음": "The sleeves partly cover the back of the hand.",
}

# ── 어깨 → 그림 지시 ──────────────────────────────────────────────────
# Q4 확정 (2026-08-20, 김정빈) — PRD 6.2.4 리포트 예시 문장을 그대로 임계값으로 쓴다:
# 「어깨 +4cm → 드롭숄더로 떨어짐」. CLAUDE.md 1절(확정 상수) 갱신 — 3명 동의 대기.
SHOULDER_DROP_THRESHOLD = 4.0
SHOULDER_DROP_PROMPT = "The shoulder seams drop below the natural shoulder line (drop shoulder)."

# 목록과 매핑이 어긋나면 그 항목만 조용히 지시가 빠진다 — 임포트 시점에 잡는다
assert set(GRADE_PROMPTS) == set(GRADE_ORDER)
assert set(LENGTH_PROMPTS) == set(LENGTH_LABELS)
assert set(SLEEVE_PROMPTS) == set(SLEEVE_LABELS)


def build_prompt(report: FitReport) -> str:
    """핏 리포트를 이미지 생성 모델에 넘길 영어 지시문으로 바꾼다.

    모르는 등급이 와도 터지지 않는다 — 프로필·리포트에 옛 문구가 남아 있다고
    이미지 생성이 죽으면 안 된다. 그 줄만 빠진다.
    """
    조각 = [BASE_PROMPT]
    for 표, 라벨 in (
        (GRADE_PROMPTS, report.fit_grade),
        (LENGTH_PROMPTS, report.length_label),
        (SLEEVE_PROMPTS, report.sleeve_label),
    ):
        문장 = 표.get(라벨)
        if 문장:
            조각.append(문장)
    if report.shoulder_diff >= SHOULDER_DROP_THRESHOLD:
        조각.append(SHOULDER_DROP_PROMPT)
    return " ".join(조각)

"""D3 · 프롬프트 변환 (PRD 6.3)

계산 결과를 이미지 생성 모델이 알아듣는 **영어 지시문**으로 바꾼다.
이미지 모델은 「가슴 여유 18cm」를 이해하지 못하므로 숫자를 말로 바꿔서 넘긴다.

⚠️ **이 문장은 사용자에게 절대 노출되지 않는다** (CLAUDE.md 6절).
⚠️ 기장·소매는 A3 가 없어 지금 항상 비어 있다 — 그래도 매핑은 미리 다 갖춰 둔다.
"""

import pytest

from fit.grade import GRADE_ORDER
from fit.report import LENGTH_LABELS, SLEEVE_LABELS, FitReport
from images.prompt import GRADE_PROMPTS, LENGTH_PROMPTS, SLEEVE_PROMPTS, build_prompt


def 리포트(**over) -> FitReport:
    base = dict(
        fit_grade="세미오버핏", gauge_level=4, chest_ease=18.0, waist_ease=24.0,
        shoulder_diff=4.0, sleeve_diff=2.0, length_label=None, sleeve_label=None,
        confidence="실측", preferred_grade="레귤러핏", grade_distance=1,
        show_preference_cta=False,
    )
    return FitReport(**(base | over))


class Test매핑에_빠진_것이_없다:
    """목록이 늘면 여기서 먼저 깨져야 한다 — 조용히 빠지면 그 등급만 지시가 사라진다"""

    def test_등급_5종이_다_있다(self):
        assert set(GRADE_PROMPTS) == set(GRADE_ORDER)

    def test_기장_5단계가_다_있다(self):
        assert set(LENGTH_PROMPTS) == set(LENGTH_LABELS)

    def test_소매_3단계가_다_있다(self):
        assert set(SLEEVE_PROMPTS) == set(SLEEVE_LABELS)

    def test_지시문이_서로_다르다(self):
        # 복사·붙여넣기로 같은 문장이 들어가면 등급 구분이 사라진다
        assert len(set(GRADE_PROMPTS.values())) == len(GRADE_PROMPTS)


class Test영어로_나간다:
    """PRD 6.3 — 이미지 생성 모델이 영어 지시를 더 정확히 따른다"""

    @pytest.mark.parametrize("등급", GRADE_ORDER)
    def test_한글이_한_글자도_섞이지_않는다(self, 등급):
        문장 = build_prompt(리포트(fit_grade=등급))
        assert not any("가" <= c <= "힣" for c in 문장), 문장

    def test_기장_소매가_채워져도_영어다(self):
        문장 = build_prompt(
            리포트(length_label="엉덩이를 반쯤 덮는 기장", sleeve_label="손등 일부 덮음")
        )
        assert not any("가" <= c <= "힣" for c in 문장), 문장


class Test항상_들어가는_요구사항:
    """PRD 6.3 — ① 얼굴·체형 유지 ② 디자인·색상·패턴 보존"""

    def test_사람을_그대로_유지하라고_말한다(self):
        assert "face" in build_prompt(리포트()).lower()

    def test_옷을_그대로_유지하라고_말한다(self):
        문장 = build_prompt(리포트()).lower()
        assert "color" in 문장 and "pattern" in 문장


class Test핏_조건:
    def test_등급이_지시문으로_바뀐다(self):
        assert GRADE_PROMPTS["세미오버핏"] in build_prompt(리포트())

    def test_등급이_바뀌면_문장도_바뀐다(self):
        assert build_prompt(리포트(fit_grade="슬림핏")) != build_prompt(리포트(fit_grade="오버핏"))

    def test_빈_줄이_공백으로_남지_않는다(self):
        # 없는 지시문을 빈 문자열로 붙이면 공백만 늘어난다
        assert "  " not in build_prompt(리포트())
        assert "  " not in build_prompt(리포트(length_label="골반에 걸치는 기본 기장"))

    def test_모르는_등급이_와도_터지지_않는다(self):
        # DB 에 옛 문구가 남아 있어도 이미지 생성이 죽으면 안 된다
        문장 = build_prompt(리포트(fit_grade="아무거나핏"))
        assert "face" in 문장.lower()


class Test아직_비어_있는_것:
    """A3(기장·소매 판정)가 없어 지금은 항상 None 이다 — Q1 · Q2"""

    def test_기장이_없으면_그_줄도_없다(self):
        assert all(p not in build_prompt(리포트()) for p in LENGTH_PROMPTS.values())

    def test_소매가_없으면_그_줄도_없다(self):
        assert all(p not in build_prompt(리포트()) for p in SLEEVE_PROMPTS.values())

    def test_채워지면_바로_들어간다(self):
        # A3 가 붙는 순간 D3 는 손대지 않아도 문장이 늘어난다
        문장 = build_prompt(
            리포트(length_label="엉덩이를 반쯤 덮는 기장", sleeve_label="손등 일부 덮음")
        )
        assert LENGTH_PROMPTS["엉덩이를 반쯤 덮는 기장"] in 문장
        assert SLEEVE_PROMPTS["손등 일부 덮음"] in 문장


class Test어깨는_아직_판정할_수_없다:
    """PRD 6.2.1 「드롭숄더는 별도 처리」 — 몇 cm부터인지가 없다 (Q4 잔여분)"""

    def test_어깨_차이가_커도_드롭숄더라고_말하지_않는다(self):
        assert "drop" not in build_prompt(리포트(shoulder_diff=12.0)).lower()

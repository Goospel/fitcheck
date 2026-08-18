"""A5 · 리포트 조립 — 계약 2

이 응답 모양에 BE-3의 D3(프롬프트 변환)와 프론트가 둘 다 의존한다. 필드 이름이
바뀌면 두 곳이 같이 깨지므로 camelCase 직렬화까지 여기서 못 박는다.

⚠️ 기장·소매 문구(lengthLabel · sleeveLabel)는 판정 기준이 미확정이라 항상 None 이다
   (docs/open-questions.md Q1 · Q2). 기준이 정해지면 아래 「미확정」 테스트가 깨지고,
   그게 채우라는 신호다.
"""

import pytest

from fit.grade import GRADE_ORDER
from fit.report import Body, Garment, build_report


def 기본_몸(**over):
    """가슴 92 / 어깨 44 / 허리 80 / 팔 58 — 셋 다 실측"""
    base = dict(
        chest=92, shoulder=44, waist=80, arm=58,
        measured=frozenset({"chest", "shoulder", "waist", "arm"}),
    )
    return Body(**(base | over))


def 기본_옷(**over):
    """가슴단면 55 → 여유 18cm → 세미오버핏"""
    base = dict(chest_width=55, shoulder=48, length=70, waist_width=52, sleeve=60)
    return Garment(**(base | over))


class Test여유량이_그대로_실린다:
    def test_A1_계산이_리포트에_들어간다(self):
        r = build_report(기본_몸(), 기본_옷())
        assert r.chest_ease == 18       # 55*2 − 92
        assert r.waist_ease == 24       # 52*2 − 80
        assert r.shoulder_diff == 4     # 48 − 44
        assert r.sleeve_diff == 2       # 60 − 58

    def test_A2_등급이_리포트에_들어간다(self):
        assert build_report(기본_몸(), 기본_옷()).fit_grade == "세미오버핏"

    def test_신축성_보정이_등급에_반영된다(self):
        r = build_report(기본_몸(), 기본_옷(chest_width=46, stretch="좋음"))
        assert r.chest_ease == 0
        assert r.fit_grade == "레귤러핏"   # 보정 없으면 슬림핏


class Test선택_입력이_없으면_숨긴다:
    def test_사용자_허리가_없으면_허리_여유가_None(self):
        r = build_report(기본_몸(waist=None), 기본_옷())
        assert r.waist_ease is None

    def test_의류_허리단면이_없으면_허리_여유가_None(self):
        assert build_report(기본_몸(), 기본_옷(waist_width=None)).waist_ease is None

    def test_소매도_같은_규칙이다(self):
        assert build_report(기본_몸(arm=None), 기본_옷()).sleeve_diff is None
        assert build_report(기본_몸(), 기본_옷(sleeve=None)).sleeve_diff is None

    def test_가슴은_항상_있다(self):
        # 가슴단면·가슴둘레는 둘 다 필수라 None 이 될 수 없다
        assert build_report(기본_몸(), 기본_옷()).chest_ease is not None


class Test신뢰도_배지:
    """어깨·가슴·허리를 직접 입력했으면 실측, 아니면 추정"""

    def test_셋_다_실측이면_실측이다(self):
        몸 = 기본_몸(measured=frozenset({"chest", "shoulder", "waist"}))
        assert build_report(몸, 기본_옷()).confidence == "실측"

    @pytest.mark.parametrize("빠진것", ["chest", "shoulder", "waist"])
    def test_하나라도_빠지면_추정이다(self, 빠진것):
        몸 = 기본_몸(measured=frozenset({"chest", "shoulder", "waist"}) - {빠진것})
        assert build_report(몸, 기본_옷()).confidence == "추정"

    def test_아무것도_실측이_아니면_추정이다(self):
        assert build_report(기본_몸(measured=frozenset()), 기본_옷()).confidence == "추정"

    def test_팔길이는_배지에_영향을_주지_않는다(self):
        # 배지 기준은 어깨·가슴·허리 셋뿐이다
        몸 = 기본_몸(measured=frozenset({"chest", "shoulder", "waist"}))
        assert build_report(몸, 기본_옷()).confidence == "실측"


class Test선호_핏_비교:
    def test_미설정이면_비교를_통째로_생략하고_CTA를_올린다(self):
        r = build_report(기본_몸(preferred_grade=None), 기본_옷())
        assert r.preferred_grade is None
        assert r.grade_distance is None
        assert r.show_preference_cta is True

    def test_설정돼_있으면_CTA를_내린다(self):
        r = build_report(기본_몸(preferred_grade="레귤러핏"), 기본_옷())
        assert r.show_preference_cta is False
        assert r.preferred_grade == "레귤러핏"

    def test_실제가_더_헐렁하면_양수다(self):
        # 선호 레귤러핏(idx 2) vs 실제 세미오버핏(idx 3)
        r = build_report(기본_몸(preferred_grade="레귤러핏"), 기본_옷())
        assert r.grade_distance == 1

    def test_실제가_더_타이트하면_음수다(self):
        r = build_report(기본_몸(preferred_grade="오버핏"), 기본_옷())
        assert r.grade_distance == -1

    def test_같으면_0이다(self):
        r = build_report(기본_몸(preferred_grade="세미오버핏"), 기본_옷())
        assert r.grade_distance == 0

    def test_모르는_선호_핏은_미설정으로_떨어진다(self):
        # 프로필에 옛 문구가 남아 있어도 500 을 내지 않는다
        r = build_report(기본_몸(preferred_grade="아무거나핏"), 기본_옷())
        assert r.grade_distance is None
        assert r.show_preference_cta is True


class Test게이지:
    @pytest.mark.parametrize(
        "가슴단면, 예상등급, 예상단계",
        [
            (44, "타이트핏", 1),      # 여유 −4
            (47, "슬림핏", 2),        # 여유 2
            (51, "레귤러핏", 3),      # 여유 10
            (55, "세미오버핏", 4),    # 여유 18
            (60, "오버핏", 5),        # 여유 28
        ],
    )
    def test_등급이_1부터_5까지의_단계로_나온다(self, 가슴단면, 예상등급, 예상단계):
        r = build_report(기본_몸(), 기본_옷(chest_width=가슴단면))
        assert r.fit_grade == 예상등급
        assert r.gauge_level == 예상단계

    def test_단계는_등급_순서와_같은_출처를_쓴다(self):
        assert GRADE_ORDER == ("타이트핏", "슬림핏", "레귤러핏", "세미오버핏", "오버핏")


class Test미확정_기장_소매:
    """docs/open-questions.md Q1 · Q2 — 기준이 정해지면 이 테스트가 깨져야 한다"""

    def test_기장_문구는_아직_비어_있다(self):
        assert build_report(기본_몸(), 기본_옷()).length_label is None

    def test_소매_문구는_아직_비어_있다(self):
        assert build_report(기본_몸(), 기본_옷()).sleeve_label is None


class Test계약_2_직렬화:
    """프론트와 D3 가 이 키를 그대로 읽는다"""

    def test_키가_camelCase로_나간다(self):
        r = build_report(기본_몸(preferred_grade="레귤러핏"), 기본_옷())
        assert r.model_dump(by_alias=True) == {
            "fitGrade": "세미오버핏",
            "gaugeLevel": 4,
            "chestEase": 18,
            "waistEase": 24,
            "shoulderDiff": 4,
            "sleeveDiff": 2,
            "lengthLabel": None,
            "sleeveLabel": None,
            "confidence": "실측",
            "preferredGrade": "레귤러핏",
            "gradeDistance": 1,
            "showPreferenceCta": False,
        }

    def test_선택_필드가_없어도_키는_남는다(self):
        # 프론트가 키 존재 여부로 분기하지 않게 항상 같은 모양을 보낸다
        r = build_report(기본_몸(waist=None, arm=None), 기본_옷())
        나간것 = r.model_dump(by_alias=True)
        assert 나간것["waistEase"] is None
        assert 나간것["sleeveDiff"] is None
        assert set(나간것) == {
            "fitGrade", "gaugeLevel", "chestEase", "waistEase", "shoulderDiff",
            "sleeveDiff", "lengthLabel", "sleeveLabel", "confidence",
            "preferredGrade", "gradeDistance", "showPreferenceCta",
        }


def test_100ms_예산_안에_든다():
    """CLAUDE.md 1절: 핏 리포트 계산 100ms 이내. 순수 산술이라 여유가 크다."""
    import time

    몸, 옷 = 기본_몸(), 기본_옷()
    시작 = time.perf_counter()
    for _ in range(1000):
        build_report(몸, 옷)
    평균_ms = (time.perf_counter() - 시작) * 1000 / 1000
    assert 평균_ms < 100, f"1건당 {평균_ms:.3f}ms"

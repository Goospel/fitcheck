"""F-10 · 사이즈 비교 — 같은 옷의 여러 사이즈를 한 응답에 담는다

심사 시연에서 M·L 게이지를 나란히 놓는 화면이 여기서 나온다 (plan.md 4절).

⚠️ **추천 규칙만이 이 모듈의 새 로직이다.** 리포트 자체는 A5(계약 2)를 그대로
   재사용하므로, 여기서 검증할 것은 「어느 사이즈를 고르는가」 하나뿐이다.
"""

import pytest

from fit.compare import compare_sizes
from fit.report import Body, Garment, build_report


def 기본_몸(**over):
    """가슴 92 / 어깨 44 / 허리 80 / 팔 58"""
    base = dict(
        chest=92, shoulder=44, waist=80, arm=58,
        measured=frozenset({"chest", "shoulder", "waist"}),
        preferred_grade="레귤러핏",
    )
    return Body(**(base | over))


def 옷(가슴단면, **over):
    base = dict(chest_width=가슴단면, shoulder=48, length=70, waist_width=52, sleeve=60)
    return Garment(**(base | over))


# 가슴둘레 92 기준 여유량 → 등급
M = 옷(51)   # 여유 10 → 레귤러핏
L = 옷(55)   # 여유 18 → 세미오버핏


class Test사이즈를_넘긴_순서대로_담는다:
    def test_두_사이즈가_다_들어온다(self):
        비교 = compare_sizes(기본_몸(), {"M": M, "L": L})
        assert [o.size_name for o in 비교.sizes] == ["M", "L"]

    def test_순서를_바꾸면_그대로_바뀐다(self):
        # 프론트가 왼쪽·오른쪽 게이지를 이 순서로 그린다
        비교 = compare_sizes(기본_몸(), {"L": L, "M": M})
        assert [o.size_name for o in 비교.sizes] == ["L", "M"]

    def test_사이즈_하나만_넘겨도_깨지지_않는다(self):
        비교 = compare_sizes(기본_몸(), {"M": M})
        assert [o.size_name for o in 비교.sizes] == ["M"]
        assert 비교.recommended_size == "M"

    def test_빈_목록이면_추천도_없다(self):
        # 의류에 사이즈가 하나도 안 등록된 경우. 500 을 내지 않는다
        비교 = compare_sizes(기본_몸(), {})
        assert 비교.sizes == []
        assert 비교.recommended_size is None


class Test리포트는_계약_2를_그대로_재사용한다:
    def test_각_항목이_build_report_와_같다(self):
        몸 = 기본_몸()
        비교 = compare_sizes(몸, {"M": M, "L": L})
        assert 비교.sizes[0].report == build_report(몸, M)
        assert 비교.sizes[1].report == build_report(몸, L)

    def test_사이즈마다_등급이_다르게_나온다(self):
        비교 = compare_sizes(기본_몸(), {"M": M, "L": L})
        assert [o.report.fit_grade for o in 비교.sizes] == ["레귤러핏", "세미오버핏"]
        assert [o.report.gauge_level for o in 비교.sizes] == [3, 4]


class Test추천은_선호_핏에_가장_가까운_사이즈:
    def test_선호와_같은_등급을_고른다(self):
        assert compare_sizes(기본_몸(preferred_grade="레귤러핏"), {"M": M, "L": L}).recommended_size == "M"

    def test_선호가_바뀌면_추천도_바뀐다(self):
        assert compare_sizes(기본_몸(preferred_grade="세미오버핏"), {"M": M, "L": L}).recommended_size == "L"

    def test_선호가_둘_다에서_멀어도_더_가까운_쪽을_고른다(self):
        # 선호 너무 작음(0) — M 레귤러(2)=2 · L 세미오버(3)=3 → M
        assert compare_sizes(기본_몸(preferred_grade="너무 작음"), {"M": M, "L": L}).recommended_size == "M"


class Test동점이면_더_헐렁한_쪽:
    """CLAUDE.md 1절 — 「큰 옷을 사게 하는 편이 작은 옷보다 낫다」와 같은 원칙"""

    def test_한_단계씩_양쪽으로_벌어지면_큰_쪽(self):
        S = 옷(47)   # 여유 2 → 슬림핏(1), 선호 레귤러핏(2) 기준 −1
        # L 은 세미오버핏(3) 기준 +1 → |차이| 동점
        비교 = compare_sizes(기본_몸(preferred_grade="레귤러핏"), {"S": S, "L": L})
        assert [o.report.grade_distance for o in 비교.sizes] == [-1, 1]
        assert 비교.recommended_size == "L"

    def test_등급까지_같으면_여유량이_큰_쪽(self):
        작은M = 옷(49)   # 여유 6 → 레귤러핏
        큰M = 옷(52)     # 여유 12 → 레귤러핏
        비교 = compare_sizes(기본_몸(preferred_grade="레귤러핏"), {"M": 작은M, "L": 큰M})
        assert [o.report.grade_distance for o in 비교.sizes] == [0, 0]
        assert 비교.recommended_size == "L"


class Test선호_핏이_없으면_추천하지_않는다:
    """어느 쪽이 나은지 정할 근거가 없다. 지어내지 않는다"""

    def test_추천이_비어_있다(self):
        assert compare_sizes(기본_몸(preferred_grade=None), {"M": M, "L": L}).recommended_size is None

    def test_대신_각_리포트가_선호_설정을_유도한다(self):
        비교 = compare_sizes(기본_몸(preferred_grade=None), {"M": M, "L": L})
        assert len(비교.sizes) == 2   # all() 이 빈 목록에 공허하게 통과하지 않게
        assert all(o.report.show_preference_cta for o in 비교.sizes)

    def test_모르는_선호_핏도_미설정과_같다(self):
        비교 = compare_sizes(기본_몸(preferred_grade="아무거나핏"), {"M": M, "L": L})
        assert 비교.recommended_size is None


class Test직렬화:
    def test_키가_camelCase로_나간다(self):
        나간것 = compare_sizes(기본_몸(), {"M": M, "L": L}).model_dump(by_alias=True)
        assert set(나간것) == {"sizes", "recommendedSize"}
        assert 나간것["recommendedSize"] == "M"
        assert set(나간것["sizes"][0]) == {"sizeName", "report"}
        assert 나간것["sizes"][0]["sizeName"] == "M"

    def test_중첩된_리포트가_계약_2_모양_그대로다(self):
        나간것 = compare_sizes(기본_몸(), {"M": M}).model_dump(by_alias=True)
        assert 나간것["sizes"][0]["report"] == {
            "fitGrade": "레귤러핏",
            "gaugeLevel": 3,
            "chestEase": 10,
            "waistEase": 24,
            "shoulderDiff": 4,
            "sleeveDiff": 2,
            "lengthLabel": None,
            "sleeveLabel": None,
            "confidence": "실측",
            "preferredGrade": "레귤러핏",
            "gradeDistance": 0,
            "showPreferenceCta": False,
        }

    def test_추천이_없어도_키는_남는다(self):
        나간것 = compare_sizes(기본_몸(preferred_grade=None), {"M": M}).model_dump(by_alias=True)
        assert 나간것["recommendedSize"] is None


def test_100ms_예산_안에_든다():
    """CLAUDE.md 1절: 핏 리포트 계산 100ms 이내. 사이즈가 늘면 그만큼 곱해진다"""
    import time

    몸, 사이즈들 = 기본_몸(), {"S": 옷(47), "M": M, "L": L, "XL": 옷(60)}
    시작 = time.perf_counter()
    for _ in range(500):
        compare_sizes(몸, 사이즈들)
    평균_ms = (time.perf_counter() - 시작) * 1000 / 500
    assert 평균_ms < 100, f"4사이즈 1건당 {평균_ms:.3f}ms"

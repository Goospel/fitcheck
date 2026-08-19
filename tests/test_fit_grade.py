"""A2 · 핏 등급 판정 — CLAUDE.md 1절 「핏 등급 임계값」

            0        6        14       24
      ------|--------|--------|--------|------>
      타이트  슬림    레귤러   세미오버   오버

    하한 포함, 상한 미포함. 여유 6cm면 레귤러핏, 14cm면 세미오버핏, 24cm면 오버핏.

    신축성 보정 — 각 구간 하한을 낮춘다
        좋음 −6cm / 약간 −4cm / 없음 0 / 미입력은 "없음"으로 간주

이 파일은 구현보다 먼저 쓰였다. 경계값이 어긋나면 리포트·프롬프트·비교 화면이 한꺼번에 깨진다.
"""

import pytest

from fit.grade import fit_grade

# 경계 바로 아래를 찍기 위한 값. 여유량은 cm 소수점이 나올 수 있다.
JUST_UNDER = 0.1


class Test보정없음:
    """임계값 0 / 6 / 14 / 24"""

    @pytest.mark.parametrize(
        "chest_ease, expected",
        [
            (-30, "너무 작음"),
            (0 - JUST_UNDER, "너무 작음"),
            (0, "슬림핏"),          # 하한 포함
            (6 - JUST_UNDER, "슬림핏"),
            (6, "레귤러핏"),         # 하한 포함
            (14 - JUST_UNDER, "레귤러핏"),
            (14, "세미오버핏"),      # 하한 포함
            (24 - JUST_UNDER, "세미오버핏"),
            (24, "오버핏"),          # 하한 포함
            (60, "오버핏"),
        ],
    )
    def test_경계값(self, chest_ease, expected):
        assert fit_grade(chest_ease, stretch="없음") == expected


class Test신축성_좋음:
    """각 구간 하한을 6cm 낮춘다 → −6 / 0 / 8 / 18"""

    @pytest.mark.parametrize(
        "chest_ease, expected",
        [
            (-6 - JUST_UNDER, "너무 작음"),
            (-6, "슬림핏"),
            (0 - JUST_UNDER, "슬림핏"),
            (0, "레귤러핏"),
            (8 - JUST_UNDER, "레귤러핏"),
            (8, "세미오버핏"),
            (18 - JUST_UNDER, "세미오버핏"),
            (18, "오버핏"),
        ],
    )
    def test_보정후_경계값(self, chest_ease, expected):
        assert fit_grade(chest_ease, stretch="좋음") == expected


class Test신축성_약간:
    """각 구간 하한을 4cm 낮춘다 → −4 / 2 / 10 / 20"""

    @pytest.mark.parametrize(
        "chest_ease, expected",
        [
            (-4 - JUST_UNDER, "너무 작음"),
            (-4, "슬림핏"),
            (2 - JUST_UNDER, "슬림핏"),
            (2, "레귤러핏"),
            (10 - JUST_UNDER, "레귤러핏"),
            (10, "세미오버핏"),
            (20 - JUST_UNDER, "세미오버핏"),
            (20, "오버핏"),
        ],
    )
    def test_보정후_경계값(self, chest_ease, expected):
        assert fit_grade(chest_ease, stretch="약간") == expected


class Test신축성_미입력:
    """CLAUDE.md 1절: 미입력은 "없음"으로 간주 — 보수적 판정"""

    @pytest.mark.parametrize("missing", [None, ""], ids=["None", "빈문자열"])
    @pytest.mark.parametrize("chest_ease", [-1, 0, 5.9, 6, 13.9, 14, 23.9, 24])
    def test_없음과_같은_결과를_낸다(self, chest_ease, missing):
        assert fit_grade(chest_ease, stretch=missing) == fit_grade(chest_ease, stretch="없음")

    def test_인자를_생략해도_없음_취급이다(self):
        assert fit_grade(5.9) == "슬림핏"

    def test_모르는_값도_없음으로_떨어진다(self):
        # 큰 옷을 사게 하는 편이 작은 옷보다 낫다 → 보정을 주지 않는 쪽이 안전
        assert fit_grade(0, stretch="매우좋음") == fit_grade(0, stretch="없음")


def test_신축성이_좋을수록_같은_여유량이_더_헐렁하게_판정된다():
    """보정 방향이 뒤집히면 조용히 반대 사이즈를 추천하게 된다."""
    순서 = ["너무 작음", "슬림핏", "레귤러핏", "세미오버핏", "오버핏"]

    for chest_ease in [-8, -4, 0, 4, 8, 12, 16, 20, 24]:
        없음 = 순서.index(fit_grade(chest_ease, stretch="없음"))
        약간 = 순서.index(fit_grade(chest_ease, stretch="약간"))
        좋음 = 순서.index(fit_grade(chest_ease, stretch="좋음"))
        assert 없음 <= 약간 <= 좋음, f"여유 {chest_ease}cm 에서 보정 방향이 뒤집혔다"


class TestPRD_문구_대조:
    """PRD 6.2.2 「이 표는 확정된 사양입니다」 — 등급명 5개를 그대로 쓴다"""

    def test_0cm_미만은_너무_작음이다(self):
        from fit.grade import fit_grade

        assert fit_grade(-1) == "너무 작음"

    def test_등급명_5개가_PRD와_같다(self):
        from fit.grade import GRADE_ORDER

        assert GRADE_ORDER == ("너무 작음", "슬림핏", "레귤러핏", "세미오버핏", "오버핏")

    def test_선호_핏으로는_4개만_고를_수_있다(self):
        # PRD 7.2 — 슬림 / 레귤러 / 세미오버 / 오버.
        # 「너무 작음」은 취향이 아니라 경고라 선택지에 없다
        from fit.grade import PREFERRED_GRADES

        assert PREFERRED_GRADES == ("슬림핏", "레귤러핏", "세미오버핏", "오버핏")

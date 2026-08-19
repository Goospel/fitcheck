"""여유량이 부동소수점 찌꺼기를 그대로 내보내지 않는다.

⚠️ **배포 서버에서 실제로 나온 값이다** (2026-08-20):

    가슴 여유 8.799999999999997cm

    54.0 × 2 − 99.2 = 8.8 이어야 하는데 이진 부동소수점이라 딱 안 떨어진다.
    프론트가 이 숫자를 그대로 그린다 — 계약 2 의 `chestEase` 가 곧 화면이다.

⚠️ **A4 가 만든 버그는 아니지만 A4 가 드러냈다.** 실측만 쓰던 때는 92.0 · 51.0 처럼
   0.0 으로 끝나는 값이라 우연히 딱 떨어졌다. 추정값은 1자리 소수라 항상 걸린다.

⚠️ **등급도 반올림한 값으로 판정한다.** 안 그러면 「여유 6.0cm · 슬림핏」처럼
   화면이 자기모순을 일으킨다 (6cm 부터 레귤러핏인데 표시는 6.0). 임계값
   0/6/14/24 는 그대로다 — 비교에 넣는 값의 정밀도를 못 박는 것뿐이다.
"""

import pytest

from fit.ease import chest_ease, shoulder_diff, sleeve_diff, waist_ease
from fit.report import Body, Garment, build_report


def 몸(**kw):
    기본 = dict(chest=99.2, shoulder=40.0, waist=80.5, arm=59.1)
    return Body(**{**기본, **kw})


def 옷(**kw):
    기본 = dict(chest_width=54.0, shoulder=48.0, length=70.0)
    return Garment(**{**기본, **kw})


class Test실제로_터졌던_값:
    def test_가슴_여유가_8_8이다(self):
        # 배포 실측 재현 — 8.799999999999997 이 아니라 8.8
        assert chest_ease(54.0, 99.2) == 8.8

    def test_리포트에도_8_8로_실린다(self):
        assert build_report(몸(), 옷()).chest_ease == 8.8


class Test네_계산식_전부:
    @pytest.mark.parametrize("옷값,몸값,기대", [
        (54.0, 99.2, 8.8),
        (51.5, 92.3, 10.7),
        (50.0, 100.1, -0.1),      # 음수도 깨끗해야 한다 (「너무 작음」 구간)
    ])
    def test_가슴(self, 옷값, 몸값, 기대):
        assert chest_ease(옷값, 몸값) == 기대

    def test_허리(self):
        assert waist_ease(44.0, 80.5) == 7.5

    def test_어깨(self):
        assert shoulder_diff(48.0, 40.1) == 7.9

    def test_소매(self):
        assert sleeve_diff(22.3, 59.1) == -36.8

    def test_없는_값은_그대로_None(self):
        # 반올림을 넣다가 None 처리를 깨면 「모름」이 0 으로 바뀐다
        assert waist_ease(None, 80.5) is None
        assert waist_ease(44.0, None) is None
        assert sleeve_diff(None, 59.1) is None
        assert sleeve_diff(22.3, None) is None


class Test소수점이_한_자리를_안_넘는다:
    """옷·몸 치수가 0.1cm 단위라 결과도 0.1cm 단위여야 한다"""

    @pytest.mark.parametrize("옷값", [50.0, 51.5, 54.3, 60.7])
    @pytest.mark.parametrize("몸값", [88.17, 99.2, 101.04, 92.35])
    def test_한_자리(self, 옷값, 몸값):
        값 = chest_ease(옷값, 몸값)
        assert round(값, 1) == 값, 값


class Test등급과_표시가_어긋나지_않는다:
    """화면이 「여유 6.0cm · 슬림핏」이라고 말하면 안 된다"""

    def test_반올림해서_6이_되면_레귤러핏이다(self):
        # 54.0×2 − 102.04 = 5.96 → 6.0 으로 보이므로 레귤러핏이어야 한다
        r = build_report(몸(chest=102.04), 옷())
        assert r.chest_ease == 6.0
        assert r.fit_grade == "레귤러핏"

    def test_반올림해도_6이_안_되면_슬림핏이다(self):
        # 54.0×2 − 102.05 = 5.95 → 5.9 (은행가 반올림) 또는 6.0. 어느 쪽이든
        # 표시값과 등급이 같은 규칙을 봐야 한다
        r = build_report(몸(chest=102.1), 옷())
        assert r.chest_ease == 5.9
        assert r.fit_grade == "슬림핏"

    def test_확정_임계값은_그대로다(self):
        # 0/6/14/24 를 건드린 게 아니다 (CLAUDE.md 1절)
        for 여유, 등급 in ((0.0, "슬림핏"), (6.0, "레귤러핏"), (14.0, "세미오버핏"), (24.0, "오버핏")):
            r = build_report(몸(chest=54.0 * 2 - 여유), 옷())
            assert (r.chest_ease, r.fit_grade) == (여유, 등급), 여유

"""A1 · 여유량 계산 — CLAUDE.md 1절 「여유량 계산식」

    가슴 여유    (의류 가슴단면 × 2) − 사용자 가슴둘레
    허리 여유    (의류 허리단면 × 2) − 사용자 허리둘레 · 입력된 경우만
    어깨 차이    의류 어깨너비 − 사용자 어깨너비
    소매 길이 차  의류 소매길이 − 사용자 팔길이
"""

import pytest

from fit.ease import chest_ease, shoulder_diff, sleeve_diff, waist_ease


class Test가슴여유:
    def test_단면을_두_배_해서_둘레에서_뺀다(self):
        assert chest_ease(garment_chest_width=52, user_chest=92) == 12

    def test_옷이_더_작으면_음수가_나온다(self):
        assert chest_ease(garment_chest_width=44, user_chest=92) == -4

    def test_소수점도_그대로_계산한다(self):
        assert chest_ease(garment_chest_width=51.5, user_chest=92) == 11.0


class Test허리여유:
    def test_단면을_두_배_해서_둘레에서_뺀다(self):
        assert waist_ease(garment_waist_width=48, user_waist=80) == 16

    def test_사용자_허리가_없으면_계산하지_않는다(self):
        assert waist_ease(garment_waist_width=48, user_waist=None) is None

    def test_의류_허리단면이_없으면_계산하지_않는다(self):
        # 허리단면은 B3에서 선택 입력이다
        assert waist_ease(garment_waist_width=None, user_waist=80) is None

    def test_둘_다_없으면_계산하지_않는다(self):
        assert waist_ease(garment_waist_width=None, user_waist=None) is None


class Test어깨차이:
    def test_의류에서_사용자를_뺀다(self):
        assert shoulder_diff(garment_shoulder=46, user_shoulder=44) == 2

    def test_옷_어깨가_더_좁으면_음수다(self):
        assert shoulder_diff(garment_shoulder=42, user_shoulder=44) == -2


class Test소매길이차:
    def test_의류에서_사용자를_뺀다(self):
        assert sleeve_diff(garment_sleeve=60, user_arm=58) == 2

    @pytest.mark.parametrize(
        "garment_sleeve, user_arm",
        [(None, 58), (60, None), (None, None)],
        ids=["의류_없음", "사용자_없음", "둘_다_없음"],
    )
    def test_한쪽이라도_없으면_계산하지_않는다(self, garment_sleeve, user_arm):
        # 소매길이는 B3에서 선택 입력이다
        assert sleeve_diff(garment_sleeve, user_arm) is None


def test_0은_없음과_다르다():
    """여유량 0은 '딱 맞음'이지 '모름'이 아니다. falsy 로 뭉개지면 안 된다."""
    assert chest_ease(garment_chest_width=46, user_chest=92) == 0
    assert waist_ease(garment_waist_width=40, user_waist=80) == 0
    assert waist_ease(garment_waist_width=40, user_waist=80) is not None

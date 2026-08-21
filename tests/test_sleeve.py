"""A3-소매 · 소매 3단계 판정 — 경계 하나는 데이터, 하나는 합의다 (Q2 종결 · 2026-08-20)

Q1(기장)과 성격이 다르다. **절반만 데이터로 풀린다.**

    소매 길이 차 = 0  →  정확히 손목      ← 사이즈코리아가 답한다
    밴드 폭 ±2cm                          ← 합의다. 인체 데이터에 답이 없다

`팔길이` 항목이 **어깨점에서 손목까지**라, A4 가 추정하는 사용자 팔길이가 곧 손목
지점이다. 그래서 「손목이 어디인가」는 지어낼 것이 없다. 「차이 몇 cm까지를 손목이라
부를 것인가」만 합의로 정했다 — ±2cm 대칭 (2026-08-20 승인).

⚠️ **비대칭을 만들지 않았다.** 입으면 소매가 팔을 타고 올라가니 평면 +2cm 는 실제로
   손목에 걸린다는 주장이 가능하지만, 그건 `fit/length.py` 의 `DRAPE_ALLOWANCE` 와
   똑같이 **실착 비교 데이터가 있어야 넣을 수 있는 보정**이다. 없으니 안 넣는다.
"""

import pytest

from fit.length import SLEEVE_BAND, SLEEVE_LABELS, sleeve_label

위, 손목, 덮음 = SLEEVE_LABELS


class Test경계:
    """하한 포함·상한 미포함 — 핏 등급 임계값(0/6/14/24)과 같은 규칙"""

    def test_차이가_0이면_손목이다(self):
        # 데이터가 답하는 유일한 점. 이게 틀리면 팔길이 정의를 잘못 읽은 것이다
        assert sleeve_label(0.0) == 손목

    def test_아래쪽_경계는_손목_쪽에_포함된다(self):
        assert sleeve_label(-2.0) == 손목
        assert sleeve_label(-2.1) == 위

    def test_위쪽_경계는_덮음_쪽에_포함된다(self):
        assert sleeve_label(2.0) == 덮음
        assert sleeve_label(1.9) == 손목

    def test_경계는_상수에서_나온다(self):
        # 숫자를 테스트에 박아 두면 상수를 바꿔도 테스트가 안 깨진다
        assert sleeve_label(-SLEEVE_BAND) == 손목
        assert sleeve_label(SLEEVE_BAND) == 덮음
        assert SLEEVE_BAND == 2.0

    @pytest.mark.parametrize("차이", [-100.0, -2.1, -50.0])
    def test_충분히_짧으면_손목_위(self, 차이):
        assert sleeve_label(차이) == 위

    @pytest.mark.parametrize("차이", [2.0, 10.0, 30.0])
    def test_충분히_길면_손등_일부_덮음(self, 차이):
        assert sleeve_label(차이) == 덮음


class Test모르는_값:
    def test_소매_길이_차가_없으면_판정하지_않는다(self):
        # 의류 소매길이도 사용자 팔길이도 선택 입력이다 (fit/ease.py)
        assert sleeve_label(None) is None


class Test반팔:
    """반팔도 세 문구 안에서 답한다 — 목록에 없는 표현을 만들지 않는다 (CLAUDE.md 1절)"""

    def test_반팔_티셔츠는_손목_위다(self):
        # 시연 의류: 소매 20.0 − 추정 팔길이 59.1
        assert sleeve_label(-39.1) == 위


class Test문구:
    def test_문구는_확정_목록_그대로다(self):
        assert SLEEVE_LABELS == ("손목 위", "손목", "손등 일부 덮음")

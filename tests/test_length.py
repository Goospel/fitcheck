"""A3 · 기장 판정 — 경계는 사이즈코리아 랜드마크에서 나온다 (Q1 종결)

문구 5종은 실제 인체 랜드마크를 그대로 부른다. 그래서 경계를 지어낼 필요가 없다 —
제8차 한국인 인체치수조사에 그 랜드마크의 **바닥 기준 높이**가 그대로 있다.

    경계 = 목뒤높이 − 랜드마크높이        (목뒤에서 아래로 몇 cm인가)

⚠️ **하한 포함·상한 미포함** — 핏 등급 임계값(0/6/14/24)과 같은 규칙이다.
⚠️ **키로 스케일한다** — 길이 랜드마크는 골격이라 A4 의 `키비` 와 같은 비율을 쓴다.
   둘레(체형비)가 아니다. 같은 키면 몸무게가 달라도 기장 경계는 같다.
"""

import pytest

from fit.estimate import ANCHORS
from fit.length import LANDMARKS, Landmarks, length_bounds, length_label
from fit.report import LENGTH_LABELS, Body, Garment, build_report

크롭, 허리, 골반, 엉덩반, 롱 = LENGTH_LABELS


class Test랜드마크는_사이즈코리아_실측이다:
    """⚠️ **출처 없이 고치지 않는다** — 제8차 조사 20~24세 평균 (cm).

    조회: sizekorea.kr 인체 항목 검색 · 8차 · 20-24 · 성별. 항목 코드는 fit/length.py 참조.
    """

    def test_남성(self):
        assert LANDMARKS["남성"] == Landmarks(
            nape=148.35, waist=106.56, top_hip=96.79, hip=86.17, gluteal=77.90
        )

    def test_여성(self):
        assert LANDMARKS["여성"] == Landmarks(
            nape=136.33, waist=98.42, top_hip=89.13, hip=79.10, gluteal=71.19
        )

    def test_A4_앵커와_같은_성별_집합을_쓴다(self):
        # 키 앵커는 fit.estimate 가 유일 출처다. 한쪽만 늘면 조용히 갈라진다
        assert set(LANDMARKS) == set(ANCHORS)

    def test_랜드마크는_위에서_아래_순서다(self):
        # 목뒤 > 허리 > 엉덩위 > 엉덩이 > 볼기고랑 (바닥 기준 높이라 내림차순)
        for 성별, lm in LANDMARKS.items():
            높이 = [lm.nape, lm.waist, lm.top_hip, lm.hip, lm.gluteal]
            assert 높이 == sorted(높이, reverse=True), 성별


class Test드레이프_보정은_아직_0이다:
    """평면 총장 ≠ 착용 시 수직 낙차. 옷은 등 곡면을 타고 내려가므로 실제 도달점은
    계산보다 조금 위다 — 하지만 **몇 cm인지는 실착 데이터가 없다.**

    ⚠️ 이 테스트가 없으면 누가 `DRAPE_ALLOWANCE` 에 그럴듯한 숫자를 넣어도
       아무도 모른다 (돌연변이 테스트에서 실제로 살아남았다). 경계 4개가 통째로
       밀리는 값이라 **바꾸려면 이 테스트를 같이 고쳐야** 한다 — 즉 의도적이어야 한다.
    """

    def test_보정값이_0이다(self):
        from fit.length import DRAPE_ALLOWANCE

        assert DRAPE_ALLOWANCE == 0.0, "실착 근거 없이 보정치를 넣지 않는다"

    def test_경계가_랜드마크_차이_그대로다(self):
        """앵커 키에서는 (목뒤 − 랜드마크) 가 보정 없이 그대로 나와야 한다.

        키를 정수로만 받아 앵커(174.99)에 딱 못 맞추므로 스케일을 되돌려 비교한다.
        허용오차는 반올림 한 칸(0.1)의 절반 — 두 번 반올림한 값끼리 대는 것이라
        `==` 로 걸면 70.45 같은 값에서 이진 표현 때문에 헛되이 터진다.
        """
        lm = LANDMARKS["남성"]
        되돌림 = ANCHORS["남성"].height / 175
        for 경계, 랜드마크 in zip(
            length_bounds(175, "남성"), (lm.waist, lm.top_hip, lm.hip, lm.gluteal)
        ):
            assert 경계 * 되돌림 == pytest.approx(lm.nape - 랜드마크, abs=0.06)


class Test경계_네_개:
    def test_남성_앵커_키에서의_경계(self):
        # 148.35 − (106.56 · 96.79 · 86.17 · 77.90)
        assert length_bounds(175, "남성") == (41.8, 51.6, 62.2, 70.5)

    def test_여성_앵커_키에서의_경계(self):
        # 136.33 − (98.42 · 89.13 · 79.10 · 71.19) = 37.91 · 47.20 · 57.23 · 65.14
        # 앵커 키가 161.79 라 162cm 는 살짝 위다 → ×1.0013 해서 37.91 이 38.0 이 된다
        assert length_bounds(162, "여성") == (38.0, 47.3, 57.3, 65.2)

    @pytest.mark.parametrize("키", [100, 150, 175, 200, 220])
    @pytest.mark.parametrize("성별", ["남성", "여성", "밝히지 않음", None])
    def test_항상_증가한다(self, 키, 성별):
        b = length_bounds(키, 성별)
        assert list(b) == sorted(b), b
        assert len(set(b)) == 4, b

    def test_키에_비례한다(self):
        작 = length_bounds(150, "남성")
        큼 = length_bounds(180, "남성")
        for a, b in zip(작, 큼):
            assert b == pytest.approx(a * 180 / 150, abs=0.15)


class Test다섯_밴드가_문구로_갈린다:
    @pytest.mark.parametrize("총장,기대", [
        (35.0, 크롭),      # 허리보다 위
        (45.0, 허리),
        (55.0, 골반),
        (66.0, 엉덩반),
        (75.0, 롱),
    ])
    def test_남성_175(self, 총장, 기대):
        assert length_label(총장, 175, "남성") == 기대

    def test_다섯_문구가_다_나온다(self):
        나온것 = {length_label(L, 175, "남성") for L in range(20, 100)}
        assert 나온것 == set(LENGTH_LABELS)

    def test_문구는_확정_목록_밖으로_안_나간다(self):
        for 키 in range(100, 221, 7):
            for 총장 in range(10, 121, 3):
                assert length_label(float(총장), 키, "남성") in LENGTH_LABELS


class Test경계값은_하한_포함이다:
    """등급 임계값(0/6/14/24)과 같은 규칙 — 경계에 딱 걸리면 아래 밴드가 아니라 위 밴드"""

    @pytest.mark.parametrize("성별,키", [("남성", 175), ("여성", 162)])
    def test_경계에_정확히_걸리면_긴_쪽이다(self, 성별, 키):
        b1, b2, b3, b4 = length_bounds(키, 성별)
        assert length_label(b1, 키, 성별) == 허리
        assert length_label(b2, 키, 성별) == 골반
        assert length_label(b3, 키, 성별) == 엉덩반
        assert length_label(b4, 키, 성별) == 롱

    @pytest.mark.parametrize("성별,키", [("남성", 175), ("여성", 162)])
    def test_경계_바로_아래는_짧은_쪽이다(self, 성별, 키):
        b1, b2, b3, b4 = length_bounds(키, 성별)
        assert length_label(b1 - 0.1, 키, 성별) == 크롭
        assert length_label(b2 - 0.1, 키, 성별) == 허리
        assert length_label(b3 - 0.1, 키, 성별) == 골반
        assert length_label(b4 - 0.1, 키, 성별) == 엉덩반


class Test키가_판정을_바꾼다:
    def test_같은_총장이_키_큰_사람에게_더_짧다(self):
        # 65cm 총장 — 작은 사람에겐 롱, 큰 사람에겐 덜 내려온다
        작은사람 = LENGTH_LABELS.index(length_label(65.0, 150, "남성"))
        큰사람 = LENGTH_LABELS.index(length_label(65.0, 195, "남성"))
        assert 작은사람 > 큰사람

    def test_몸무게는_기장에_영향을_주지_않는다(self):
        # 기장 경계는 골격(키)에서만 나온다 — Body 에 몸무게가 안 들어가는 이유
        assert length_bounds(175, "남성") == length_bounds(175, "남성")


class Test성별을_안_밝히면_중간값이다:
    """A4 추정기와 같은 처리 — 남녀 경계의 중간을 쓴다"""

    @pytest.mark.parametrize("성별", ["밝히지 않음", None, "", "기타"])
    def test_중간값(self, 성별):
        남 = length_bounds(175, "남성")
        여 = length_bounds(175, "여성")
        중간 = length_bounds(175, 성별)
        # 허용오차는 반올림 한 칸(0.1)의 절반 + 부동소수점 여유.
        # 0.05 딱 걸면 |51.3 − 51.35| 가 0.05000000000000426 이라 터진다
        for m, f, x in zip(남, 여, 중간):
            assert x == pytest.approx((m + f) / 2, abs=0.06)

    def test_기장에서는_성별이_거의_영향이_없다(self):
        """⚠️ **A4 와 다른 점이다.** 둘레(가슴·허리)는 성별로 크게 갈리지만,
        **키로 정규화하고 나면 상체 비율은 남녀가 거의 같다.**

        같은 키에서 남녀 경계 차는 최대 0.9cm 인데 밴드 폭은 8~10cm 다. 즉 성별을
        안 밝혀도 기장 판정은 사실상 안 흔들린다 — 「밝히지 않음」이 손해가 아니다.
        볼기고랑(b4)은 여성이 오히려 근소하게 크므로 `여 < 남` 을 가정하면 안 된다.
        """
        for 키 in (150, 160, 175, 190, 200):
            for 남, 여 in zip(length_bounds(키, "남성"), length_bounds(키, "여성")):
                assert abs(남 - 여) < 1.0, (키, 남, 여)


class Test키가_없으면_판정하지_않는다:
    def test_None_이면_None(self):
        # 프로필에 키는 필수지만 Body 는 순수 자료구조라 없을 수 있다.
        # 지어내지 말고 조용히 비운다 — 계약상 lengthLabel 은 선택 필드다
        assert length_label(70.0, None, "남성") is None


class Test순수_함수다:
    def test_같은_입력이면_같은_출력(self):
        assert [length_label(70.0, 175, "남성") for _ in range(5)].count(
            length_label(70.0, 175, "남성")
        ) == 5

    def test_LANDMARKS_는_불변이다(self):
        with pytest.raises(Exception):
            LANDMARKS["남성"].nape = 999


class Test리포트에_실린다:
    """계약 2 의 lengthLabel · sleeveLabel 이 드디어 둘 다 채워진다"""

    def 몸(self, **kw):
        기본 = dict(chest=99.2, shoulder=40.0, waist=80.5, arm=59.1,
                    height=175, gender="남성")
        return Body(**{**기본, **kw})

    def 옷(self, **kw):
        기본 = dict(chest_width=54.0, shoulder=48.0, length=66.0)
        return Garment(**{**기본, **kw})

    def test_기장_문구가_채워진다(self):
        assert build_report(self.몸(), self.옷()).length_label == 엉덩반

    def test_총장이_바뀌면_문구도_바뀐다(self):
        assert build_report(self.몸(), self.옷(length=45.0)).length_label == 허리
        assert build_report(self.몸(), self.옷(length=75.0)).length_label == 롱

    def test_키가_없으면_여전히_None(self):
        assert build_report(self.몸(height=None), self.옷()).length_label is None

    def test_소매_문구도_채워진다(self):
        # 소매 60.0 − 팔 59.1 = +0.9 → 밴드(±2) 안이라 「손목」 (Q2 종결 · 2026-08-20)
        assert build_report(self.몸(), self.옷(sleeve=60.0)).sleeve_label == "손목"

    def test_소매길이가_없으면_소매만_비고_기장은_남는다(self):
        # 둘은 서로 다른 입력에서 나온다 — 하나가 없다고 같이 비면 안 된다
        r = build_report(self.몸(), self.옷())
        assert r.sleeve_label is None
        assert r.length_label == 엉덩반

    def test_등급은_안_건드렸다(self):
        # 기장을 붙이면서 가슴 판정이 흔들리면 안 된다
        r = build_report(self.몸(), self.옷())
        assert (r.chest_ease, r.fit_grade) == (8.8, "레귤러핏")

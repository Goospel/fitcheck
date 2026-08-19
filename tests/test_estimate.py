"""A4 · 신체 치수 추정 (docs/open-questions.md Q3 종결분)

⚠️ **이 파일의 존재 이유는 「숫자의 출처」다.** 계수를 지어내면 리포트가 조용히
   틀리고 사용자가 틀린 사이즈를 산다 (CLAUDE.md 1절). 그래서 앵커 값이 실제
   사이즈코리아 8차 조사 수치인지를 **테스트가 못 박는다** — 누가 「더 나은 값」으로
   슬쩍 바꾸면 여기서 걸린다.

⚠️ 스케일 법칙(길이는 키에, 둘레는 체형에)은 **가정이다.** 가정이라서 더더욱
   성질(단조성·대칭성·범위)을 테스트로 고정한다 — 식을 바꿔도 이 성질이 깨지면 안 된다.
"""

import pytest

from api.profile import GENDERS
from fit.estimate import ANCHORS, Estimated, estimate_body

남 = "남성"
여 = "여성"
비공개 = "밝히지 않음"


class Test앵커가_사이즈코리아_실측값이다:
    """제8차 한국인 인체치수조사(2020~) · 20~24세. **지어낸 숫자가 아니다.**"""

    def test_남자_앵커(self):
        a = ANCHORS[남]
        assert (a.height, a.weight) == (174.99, 72.68)
        assert (a.chest, a.waist) == (101.04, 82.06)
        assert (a.shoulder, a.arm) == (40.01, 59.06)

    def test_여자_앵커(self):
        a = ANCHORS[여]
        assert (a.height, a.weight) == (161.79, 55.31)
        assert (a.chest, a.waist) == (88.17, 72.62)
        assert (a.shoulder, a.arm) == (34.70, 54.10)

    def test_성별_목록과_어긋나지_않는다(self):
        # 「밝히지 않음」은 두 앵커의 중간이라 표에 없다. 나머지 둘은 반드시 있어야 한다
        assert set(ANCHORS) == set(GENDERS) - {비공개}


class Test평균_체형이면_평균_치수가_나온다:
    """앵커 자신을 넣으면 앵커가 나와야 한다 — 스케일 식이 1을 곱하는지 보는 것"""

    @pytest.mark.parametrize("성별", [남, 여])
    def test_앵커를_넣으면_앵커가_나온다(self, 성별):
        a = ANCHORS[성별]
        결과 = estimate_body(round(a.height), round(a.weight), 성별)
        for 이름 in ("chest", "shoulder", "waist", "arm"):
            assert getattr(결과, 이름) == pytest.approx(getattr(a, 이름), abs=0.6), 이름


class Test키가_길이를_움직인다:
    """어깨너비·팔길이는 키에 비례한다"""

    def test_키가_크면_어깨가_넓다(self):
        작 = estimate_body(165, 70, 남)
        큼 = estimate_body(185, 70, 남)
        assert 큼.shoulder > 작.shoulder
        assert 큼.arm > 작.arm

    def test_몸무게는_길이를_안_건드린다(self):
        마름 = estimate_body(175, 55, 남)
        무거움 = estimate_body(175, 95, 남)
        assert 마름.shoulder == 무거움.shoulder
        assert 마름.arm == 무거움.arm

    def test_비례한다(self):
        # 키가 10% 크면 어깨도 10% 넓다
        기준 = estimate_body(170, 70, 남)
        큼 = estimate_body(187, 70, 남)
        assert 큼.shoulder / 기준.shoulder == pytest.approx(1.1, abs=0.001)


class Test체형이_둘레를_움직인다:
    """가슴·허리는 **키와 몸무게를 같이** 본다. 몸무게만 보면 키 큰 사람이 늘 뚱뚱해진다"""

    def test_무거우면_가슴이_크다(self):
        마름 = estimate_body(175, 55, 남)
        무거움 = estimate_body(175, 95, 남)
        assert 무거움.chest > 마름.chest
        assert 무거움.waist > 마름.waist

    def test_같은_몸무게에_키가_크면_더_마르다(self):
        # 175cm 70kg 과 190cm 70kg 은 같은 체격이 아니다
        작 = estimate_body(175, 70, 남)
        큼 = estimate_body(190, 70, 남)
        assert 큼.chest < 작.chest
        assert 큼.waist < 작.waist

    def test_키와_몸무게가_같은_비율로_커지면_둘레도_같은_비율(self):
        # 체형이 그대로면(닮은꼴) 둘레도 키에 비례해야 한다
        기준 = estimate_body(170, 60, 남)
        # 키 ×1.1 이면 부피는 ×1.1³ 이라 몸무게도 ×1.331
        닮음 = estimate_body(187, 80, 남)
        assert 닮음.chest / 기준.chest == pytest.approx(1.1, abs=0.02)


class Test성별:
    def test_여자가_남자보다_작다(self):
        # 같은 키·몸무게라도 성별에 따라 체형 비율이 다르다
        남자 = estimate_body(170, 65, 남)
        여자 = estimate_body(170, 65, 여)
        assert 여자.shoulder < 남자.shoulder

    def test_밝히지_않으면_두_앵커의_중간이다(self):
        # 정보가 없을 때 한쪽으로 기울이지 않는다
        남자 = estimate_body(170, 65, 남)
        여자 = estimate_body(170, 65, 여)
        중간 = estimate_body(170, 65, 비공개)
        for 이름 in ("chest", "shoulder", "waist", "arm"):
            낮, 높 = sorted((getattr(남자, 이름), getattr(여자, 이름)))
            assert 낮 < getattr(중간, 이름) < 높, 이름

    def test_모르는_성별도_중간으로_받는다(self):
        # 옛 프로필에 없는 값이 남아 있어도 추정이 죽으면 안 된다
        assert estimate_body(170, 65, None) == estimate_body(170, 65, 비공개)
        assert estimate_body(170, 65, "기타") == estimate_body(170, 65, 비공개)


class Test입력_범위_끝에서도_성립한다:
    """CLAUDE.md 1절 확정 범위 — 키 100~220 · 몸무게 30~200"""

    @pytest.mark.parametrize("키", [100, 220])
    @pytest.mark.parametrize("몸무게", [30, 200])
    @pytest.mark.parametrize("성별", [남, 여, 비공개])
    def test_끝값에서도_양수다(self, 키, 몸무게, 성별):
        r = estimate_body(키, 몸무게, 성별)
        for 이름 in ("chest", "shoulder", "waist", "arm"):
            assert getattr(r, 이름) > 0, 이름

    def test_극단값에서도_사람_치수_범위를_벗어나지_않는다(self):
        # 100cm 200kg 같은 조합은 현실에 없지만 입력은 가능하다. 터지지만 않으면 된다
        r = estimate_body(100, 200, 남)
        assert r.chest > r.waist * 0.5      # 순서가 뒤집히거나 0 이 되지 않는다


class Test순수_함수다:
    """CLAUDE.md 6절 — fit/ 은 DB·네트워크·시간에 의존하지 않는다"""

    def test_같은_입력이면_같은_출력(self):
        assert estimate_body(175, 70, 남) == estimate_body(175, 70, 남)

    def test_결과는_못_바꾼다(self):
        r = estimate_body(175, 70, 남)
        assert isinstance(r, Estimated)
        with pytest.raises(Exception):
            r.chest = 999            # frozen dataclass

    def test_소수점이_지저분하지_않다(self):
        # 프론트가 그대로 그린다. 41.00000000000001 이 보이면 안 된다
        r = estimate_body(178, 74, 남)
        for 이름 in ("chest", "shoulder", "waist", "arm"):
            값 = getattr(r, 이름)
            assert round(값, 1) == 값, f"{이름}={값}"

"""D2 · 전신 사진 비전 검증 — 판정 해석만 순수 함수로 잘라 시험한다

비전 호출 자체는 네트워크라 여기서 안 부른다. **모델이 뱉은 dict 를 어떻게 읽는가**가
사용자에게 보이는 전부고, 거기 실수가 나면 멀쩡한 사진이 거부된다.

⚠️ **애매하면 통과시킨다 (fail-open).** 업로드는 서비스의 입구다 — 비전 모델이
   흔들린다고 입구를 막으면, 막힌 사람은 우회로가 없다. 해상도 검사는 그대로 돌고
   있고, 최악의 경우는 「이상한 사진으로 이상한 결과가 나온다」다. 그건 되돌릴 수
   있지만 「가입은 됐는데 사진을 못 올린다」는 못 되돌린다.
"""

import pytest

from images.vision import REJECTIONS, verdict
from tests.test_photo import 사진, 크기
from tests.test_photo_upload import 옷_등록, 올리기, 인증   # noqa: F401 — 인증은 픽스처다


def 판정(**kw) -> dict:
    """전부 통과하는 응답에서 필요한 것만 뒤집는다"""
    return {"person": True, "full_body": True, "safe": True} | kw


class Test통과:
    def test_셋_다_참이면_통과(self):
        assert verdict(판정()) is None

    def test_모르는_키가_섞여도_통과(self):
        # 모델이 스키마를 늘려도 거부 사유가 되면 안 된다
        assert verdict(판정(facing="side", reason="옆모습입니다")) is None


class Test거부:
    def test_사람이_없으면_거부(self):
        assert verdict(판정(person=False)) == REJECTIONS["person"]

    def test_전신이_아니면_거부(self):
        assert verdict(판정(full_body=False)) == REJECTIONS["full_body"]

    def test_부적절하면_거부(self):
        assert verdict(판정(safe=False)) == REJECTIONS["safe"]

    def test_거부_사유는_한국어다(self):
        # 사용자에게 그대로 보이는 문장이다 (CLAUDE.md 6절)
        for 문장 in REJECTIONS.values():
            assert any("가" <= 글자 <= "힣" for 글자 in 문장), 문장

    def test_모델이_쓴_문장을_그대로_쓰지_않는다(self):
        # reason 을 사용자에게 흘리면 문구가 매번 달라지고 통제가 안 된다
        assert verdict(판정(person=False, reason="아무 말이나")) == REJECTIONS["person"]


class Test우선순위:
    """여러 개가 걸려도 **하나만** 말한다 — 사람이 없으면 전신 여부는 의미가 없다"""

    def test_사람이_없으면_그것부터_말한다(self):
        assert verdict(판정(person=False, full_body=False)) == REJECTIONS["person"]

    def test_부적절이_전신보다_앞선다(self):
        assert verdict(판정(full_body=False, safe=False)) == REJECTIONS["safe"]


class Test애매하면_통과시킨다:
    """fail-open — 판정을 못 하는 것과 「나쁜 사진이다」는 다르다"""

    @pytest.mark.parametrize("응답", [
        {},                                   # 빈 응답
        {"person": True},                     # 키가 모자람
        {"person": "yes", "full_body": "yes", "safe": "yes"},   # 타입이 다름
        {"person": None, "full_body": None, "safe": None},
    ])
    def test_읽을_수_없으면_통과(self, 응답):
        assert verdict(응답) is None

    def test_None_이면_통과(self):
        # 호출 자체가 실패했을 때 들어오는 값
        assert verdict(None) is None

    def test_한_칸만_망가져도_판정을_통째로_포기한다(self):
        """⚠️ **부분적으로도 믿지 않는다.** 스키마를 안 지킨 응답에서 `person=False`
        가 진짜 판정인지 모델이 통째로 헛소리를 한 건지 구분할 방법이 없다.

        돌연변이 테스트가 이 구멍을 찾아냈다 — 「bool 이 아니면 건너뛴다」로 바꿔도
        기존 테스트가 다 통과했다. 전부 망가진 응답만 시험하고 **섞인 응답**을
        안 시험했기 때문이다.
        """
        assert verdict({"safe": "yes", "person": False, "full_body": True}) is None
        assert verdict({"safe": True, "person": None, "full_body": False}) is None


class Test업로드_경로에_실제로_걸린다:
    """판정이 맞아도 **안 불리면** 아무 일도 안 일어난다. 연결이 진짜 논리다"""

    @pytest.fixture
    def 불린것(self, monkeypatch) -> list[bytes]:
        """진짜 호출 대신 넘어온 바이트만 받아 둔다 — 테스트는 외부 API 를 안 부른다"""
        기록: list[bytes] = []

        async def 가짜(raw: bytes) -> None:
            기록.append(raw)

        monkeypatch.setattr("api.photos.check_person_photo", 가짜)
        return 기록

    async def test_전신_사진에는_걸린다(self, client, 인증, 불린것):
        assert (await 올리기(client, 인증)).status_code == 200
        assert len(불린것) == 1

    async def test_의류_제품컷에는_안_걸린다(self, client, 인증, 불린것):
        # 제품컷에 사람이 없는 것이 정상이다. 걸면 의류 등록이 통째로 막힌다
        옷 = await 옷_등록(client, 인증)
        assert (await 올리기(client, 인증, 의류_id=옷)).status_code == 200
        assert 불린것 == []

    async def test_EXIF_를_편_뒤의_바이트가_간다(self, client, 인증, 불린것):
        """⚠️ 순서가 논리다 — 원본을 넘기면 눕혀 저장된 폰 사진이 모델 눈에도
        누워 보여 「전신 아님」으로 오판된다. 정규화가 **먼저**여야 한다."""
        await 올리기(client, 인증, raw=사진(768, 512, orientation=6))
        assert 크기(불린것[0]) == (512, 768)

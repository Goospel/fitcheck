"""B5 · 히스토리 + B6 · 결과 조회

생성이 10분 걸리는 이상 **결과를 나중에 찾을 유일한 경로**라 PRD가 P0로 둔 기능이다
(5.2 F-07 · 7.5절).

⚠️ 이미지 파이프라인이 아직 없다 — 지금 만들어지는 피팅은 전부 「리포트만」이다.
   상태 분기는 `image_job` 행을 직접 넣어 확인한다.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Fitting, ImageJob

의류 = {"kind": "티셔츠", "sizeName": "M", "shoulder": 48.0, "chestWidth": 51.0, "length": 70.0}
프로필 = {
    "height": 175, "weight": 70, "gender": "남성",
    "shoulder": 44.0, "chest": 92.0, "waist": 80.0, "arm": 58.0, "preferredGrade": "레귤러핏",
}


@pytest.fixture
async def 인증(client):
    r = await client.post("/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
async def 피팅하나(client, 인증):
    await client.put("/profile", json=프로필, headers=인증)
    옷 = (await client.post("/garments", json=의류, headers=인증)).json()["id"]
    피팅 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
    return 인증, 피팅["id"]


async def 잡_넣기(engine, fitting_id: str, status: str, image_path: str | None = None):
    """이미지 파이프라인이 아직 없어 잡을 직접 넣는다"""
    async with AsyncSession(engine) as s:
        s.add(ImageJob(fitting_id=uuid.UUID(fitting_id), status=status))
        if image_path:
            f = await s.get(Fitting, uuid.UUID(fitting_id))
            f.image_path = image_path
        await s.commit()


class Test목록:
    async def test_토큰이_필요하다(self, client):
        assert (await client.get("/fittings")).status_code == 401

    async def test_만든_피팅이_보인다(self, client, 피팅하나):
        인증, 피팅_id = 피팅하나
        본문 = (await client.get("/fittings", headers=인증)).json()
        assert [i["id"] for i in 본문["items"]] == [피팅_id]

    async def test_어떤_옷인지_같이_온다(self, client, 피팅하나):
        # 목록을 그리려고 의류를 하나씩 다시 물어보게 하지 않는다
        인증, _ = 피팅하나
        옷 = (await client.get("/fittings", headers=인증)).json()["items"][0]["garment"]
        assert (옷["kind"], 옷["sizeName"]) == ("티셔츠", "M")

    async def test_리포트도_같이_온다(self, client, 피팅하나):
        인증, _ = 피팅하나
        항목 = (await client.get("/fittings", headers=인증)).json()["items"][0]
        assert 항목["report"]["fitGrade"] == "레귤러핏"

    async def test_최신이_위로_온다(self, client, 피팅하나):
        인증, 첫번째 = 피팅하나
        옷 = (await client.post("/garments", json=의류 | {"sizeName": "L"}, headers=인증)).json()["id"]
        둘째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()["id"]
        본문 = (await client.get("/fittings", headers=인증)).json()
        assert [i["id"] for i in 본문["items"]] == [둘째, 첫번째]

    async def test_남의_피팅은_안_보인다(self, client, 피팅하나):
        인증, _ = 피팅하나
        남 = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True})
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        assert (await client.get("/fittings", headers=헤더)).json()["items"] == []


class Test상태:
    """계약 3 — 대기 / 생성중 / 완료 / 실패 / 리포트만"""

    async def test_잡이_없으면_리포트만이다(self, client, 피팅하나):
        # 사진 없이 만든 경로 (F-09). 기다릴 것이 없다
        인증, _ = 피팅하나
        assert (await client.get("/fittings", headers=인증)).json()["items"][0]["status"] == "리포트만"

    @pytest.mark.parametrize("상태", ["대기", "생성중", "완료", "실패"])
    async def test_잡_상태가_그대로_올라온다(self, client, 피팅하나, db_engine, 상태):
        인증, 피팅_id = 피팅하나
        await 잡_넣기(db_engine, 피팅_id, 상태)
        assert (await client.get("/fittings", headers=인증)).json()["items"][0]["status"] == 상태

    async def test_상태로_거를_수_있다(self, client, 피팅하나, db_engine):
        인증, 피팅_id = 피팅하나
        await 잡_넣기(db_engine, 피팅_id, "완료")
        assert len((await client.get("/fittings?status=완료", headers=인증)).json()["items"]) == 1
        assert len((await client.get("/fittings?status=실패", headers=인증)).json()["items"]) == 0

    async def test_리포트만도_거를_수_있다(self, client, 피팅하나):
        인증, _ = 피팅하나
        assert len((await client.get("/fittings?status=리포트만", headers=인증)).json()["items"]) == 1

    async def test_모르는_상태로_거르면_거부한다(self, client, 피팅하나):
        인증, _ = 피팅하나
        assert (await client.get("/fittings?status=아무거나", headers=인증)).status_code == 422


class Test뱃지_개수:
    """PRD 7.5 — 다른 페이지에 있어도 헤더에 「내 피팅 (1)」 이 떠야 한다"""

    async def test_상태_5종이_항상_다_나온다(self, client, 피팅하나):
        # 0 이어도 키가 사라지지 않아야 프론트가 분기하지 않는다
        인증, _ = 피팅하나
        assert set((await client.get("/fittings", headers=인증)).json()["counts"]) == {
            "대기", "생성중", "완료", "실패", "리포트만",
        }

    async def test_세어진다(self, client, 피팅하나, db_engine):
        인증, 피팅_id = 피팅하나
        await 잡_넣기(db_engine, 피팅_id, "완료")
        개수 = (await client.get("/fittings", headers=인증)).json()["counts"]
        assert 개수["완료"] == 1
        assert 개수["리포트만"] == 0

    async def test_개수는_거르기와_무관하다(self, client, 피팅하나, db_engine):
        # 필터를 걸어도 뱃지는 전체를 세야 한다
        인증, 피팅_id = 피팅하나
        await 잡_넣기(db_engine, 피팅_id, "완료")
        본문 = (await client.get("/fittings?status=실패", headers=인증)).json()
        assert 본문["items"] == []
        assert 본문["counts"]["완료"] == 1

    async def test_남의_것은_안_세어진다(self, client, 피팅하나):
        인증, _ = 피팅하나
        남 = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True})
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        assert (await client.get("/fittings", headers=헤더)).json()["counts"]["리포트만"] == 0


class TestB6_결과_조회:
    """이미지 + 리포트 통합. **이미지 없는 경로(F-09)에서도 성립할 것**"""

    async def test_이미지가_없어도_리포트는_나온다(self, client, 피팅하나):
        인증, 피팅_id = 피팅하나
        본문 = (await client.get(f"/fittings/{피팅_id}", headers=인증)).json()
        assert 본문["report"]["fitGrade"] == "레귤러핏"
        assert 본문["imagePath"] is None
        assert 본문["status"] == "리포트만"

    async def test_이미지가_생기면_같이_나온다(self, client, 피팅하나, db_engine):
        인증, 피팅_id = 피팅하나
        await 잡_넣기(db_engine, 피팅_id, "완료", image_path="fittings/abc.png")
        본문 = (await client.get(f"/fittings/{피팅_id}", headers=인증)).json()
        assert 본문["imagePath"] == "fittings/abc.png"
        assert 본문["status"] == "완료"

    async def test_실패해도_리포트는_남는다(self, client, 피팅하나, db_engine):
        # PRD 7.5 — 사용자가 빈손으로 돌아가지 않게
        인증, 피팅_id = 피팅하나
        await 잡_넣기(db_engine, 피팅_id, "실패")
        본문 = (await client.get(f"/fittings/{피팅_id}", headers=인증)).json()
        assert 본문["status"] == "실패"
        assert 본문["report"]["chestEase"] == 10

    async def test_어떤_옷인지_같이_온다(self, client, 피팅하나):
        인증, 피팅_id = 피팅하나
        본문 = (await client.get(f"/fittings/{피팅_id}", headers=인증)).json()
        assert 본문["garment"]["sizeName"] == "M"

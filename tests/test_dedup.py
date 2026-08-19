"""D6 · 중복 생성 방지 (plan.md 6절 — **자르지 말 것**으로 표시된 항목)

생성 1건이 **최대 10분 + 유료 API 호출**이다. 시연 중 같은 조합을 두 번 누르면
그대로 비용이고, 심사위원 앞에서 10분을 기다리는 사고가 난다.

⚠️ 재사용이 **틀리면 더 나쁘다.** 두 가지를 같이 지킨다:
   ① 실패한 결과를 돌려주면 재시도가 영영 막힌다
   ② 프로필이 바뀌었는데 옛 판정을 돌려주면 사용자는 틀린 사이즈를 산다
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Fitting, ImageJob, User

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
async def 준비(client, 인증):
    await client.put("/profile", json=프로필, headers=인증)
    옷 = (await client.post("/garments", json=의류, headers=인증)).json()["id"]
    return 인증, 옷


async def 잡_넣기(engine, fitting_id: str, status: str, image_path: str | None = None):
    async with AsyncSession(engine) as s:
        s.add(ImageJob(fitting_id=uuid.UUID(fitting_id), status=status))
        if image_path:
            (await s.get(Fitting, uuid.UUID(fitting_id))).image_path = image_path
        await s.commit()


class Test같은_요청은_한_번만:
    async def test_두_번_눌러도_같은_결과가_온다(self, client, 준비):
        인증, 옷 = 준비
        첫째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        둘째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 둘째.json()["id"] == 첫째.json()["id"]

    async def test_만들었으면_201_재사용이면_200(self, client, 준비):
        # 프론트가 「새로 만드는 중」과 「이미 있던 것」을 구분해야 스피너를 안 띄운다
        인증, 옷 = 준비
        assert (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).status_code == 201
        assert (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).status_code == 200

    async def test_히스토리가_두_줄이_되지_않는다(self, client, 준비):
        인증, 옷 = 준비
        for _ in range(3):
            await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert len((await client.get("/fittings", headers=인증)).json()["items"]) == 1

    async def test_재사용해도_응답_모양이_같다(self, client, 준비):
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        둘째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        assert set(둘째) == set(첫째)
        assert 둘째["report"] == 첫째["report"]


class Test재사용하면_안_되는_것:
    async def test_다른_사이즈는_새로_만든다(self, client, 준비):
        인증, M = 준비
        L = (await client.post("/garments", json=의류 | {"sizeName": "L", "chestWidth": 55.0},
                               headers=인증)).json()["id"]
        첫째 = await client.post("/fittings", json={"garmentId": M}, headers=인증)
        둘째 = await client.post("/fittings", json={"garmentId": L}, headers=인증)
        assert 둘째.status_code == 201
        assert 둘째.json()["id"] != 첫째.json()["id"]

    async def test_남의_결과를_돌려주지_않는다(self, client, 준비):
        인증, 옷 = 준비
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        남 = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True})
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        await client.put("/profile", json=프로필, headers=헤더)
        # 남의 의류는 애초에 보이지 않는다
        assert (await client.post("/fittings", json={"garmentId": 옷}, headers=헤더)).status_code == 404

    async def test_남의_판정을_가져다_쓰지_않는다(self, client, 준비, db_engine):
        """의류가 사용자별 행이라 지금은 `_owned` 가 먼저 막는다.

        그래도 소유자 조건을 남겨 두는 이유 — 의류가 공용 카탈로그가 되는 순간
        같은 `garment_id` 에 남의 피팅이 붙고, 조건이 없으면 **남의 판정이 샌다.**
        """
        인증, 옷 = 준비
        남 = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True})
        assert 남.status_code == 201

        # 내가 만들 리포트와 **똑같은** 판정을 남의 이름으로 미리 박아 둔다
        # (compare 는 저장하지 않으므로 내 히스토리는 비어 있는 채로 리포트만 얻는다)
        내판정 = (await client.post("/fittings/compare", json={"garmentIds": [옷]},
                                   headers=인증)).json()["sizes"][0]["report"]
        async with AsyncSession(db_engine) as s:
            남_id = (await s.execute(select(User.id).where(User.email == "c@d.com"))).scalar_one()
            s.add(Fitting(user_id=남_id, garment_id=uuid.UUID(옷), report=내판정))
            await s.commit()

        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.status_code == 201          # 남의 것을 재사용하지 않고 새로 만든다
        assert r.json()["report"] == 내판정

    async def test_프로필이_바뀌면_새로_만든다(self, client, 준비):
        # 판정이 달라졌는데 옛 결과를 돌려주면 사용자가 틀린 사이즈를 산다
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        await client.put("/profile", json=프로필 | {"chest": 70.0}, headers=인증)
        둘째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 둘째.status_code == 201
        assert 둘째.json()["id"] != 첫째["id"]
        assert 둘째.json()["report"]["chestEase"] != 첫째["report"]["chestEase"]

    async def test_프로필을_되돌리면_옛것을_다시_쓴다(self, client, 준비):
        # 판정이 같아졌으면 같은 것이다. 「몇 번 고쳤는가」는 상관없다
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        await client.put("/profile", json=프로필 | {"chest": 70.0}, headers=인증)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        await client.put("/profile", json=프로필, headers=인증)
        셋째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 셋째.status_code == 200
        assert 셋째.json()["id"] == 첫째["id"]


class Test잡_상태에_따라:
    """여기가 D6 의 값이 나오는 자리다 — 10분짜리 잡을 두 번 돌리지 않는다"""

    async def test_완료된_이미지는_그대로_재사용한다(self, client, 준비, db_engine):
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        await 잡_넣기(db_engine, 첫째["id"], "완료", image_path="fittings/abc.png")
        둘째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 둘째.status_code == 200
        assert 둘째.json()["imagePath"] == "fittings/abc.png"      # 10분과 비용을 아꼈다
        assert 둘째.json()["status"] == "완료"

    @pytest.mark.parametrize("상태", ["대기", "생성중"])
    async def test_돌고_있는_잡을_두_번_큐에_넣지_않는다(self, client, 준비, db_engine, 상태):
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        await 잡_넣기(db_engine, 첫째["id"], 상태)
        둘째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 둘째.status_code == 200
        assert 둘째.json()["id"] == 첫째["id"]
        assert 둘째.json()["status"] == 상태

    async def test_실패한_것은_재사용하지_않는다(self, client, 준비, db_engine):
        # 실패를 돌려주면 사용자가 영영 다시 시도할 수 없다
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        await 잡_넣기(db_engine, 첫째["id"], "실패")
        둘째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 둘째.status_code == 201
        assert 둘째.json()["id"] != 첫째["id"]

    async def test_실패_뒤_새로_만든_것은_다시_재사용된다(self, client, 준비, db_engine):
        # 실패한 옛 행 때문에 이후 요청이 계속 새로 만들면 중복 방지가 무의미해진다
        인증, 옷 = 준비
        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        await 잡_넣기(db_engine, 첫째["id"], "실패")
        둘째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        셋째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 셋째.status_code == 200
        assert 셋째.json()["id"] == 둘째["id"]


class Test비교는_영향받지_않는다:
    async def test_비교는_저장하지_않으므로_중복도_없다(self, client, 준비):
        인증, M = 준비
        L = (await client.post("/garments", json=의류 | {"sizeName": "L", "chestWidth": 55.0},
                               headers=인증)).json()["id"]
        for _ in range(2):
            r = await client.post("/fittings/compare", json={"garmentIds": [M, L]}, headers=인증)
            assert r.status_code == 200
        assert (await client.get("/fittings", headers=인증)).json()["items"] == []

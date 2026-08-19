"""B4 · 핏 분석 API + F-10 · 사이즈 비교 엔드포인트

프로필 + 의류 → A5 → 리포트. 계산은 이미 `fit/` 에 있고 여기는 **꺼내 쓰는 층**이다.

⚠️ A4(치수 추정기)가 아직 없다 — 가슴·어깨를 직접 입력하지 않은 프로필은
   리포트를 낼 수 없다. 지어낸 값으로 채우지 않고 **명시적으로 거절**한다.
"""

import uuid

import pytest

의류 = {"kind": "티셔츠", "sizeName": "M", "shoulder": 48.0, "chestWidth": 51.0, "length": 70.0}
프로필 = {
    "height": 175, "weight": 70, "gender": "남성",
    "shoulder": 44.0, "chest": 92.0, "waist": 80.0, "arm": 58.0,
    "preferredGrade": "레귤러핏",
}


@pytest.fixture
async def 인증(client):
    r = await client.post("/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
async def 준비(client, 인증):
    """프로필 + M 사이즈 하나까지 갖춘 상태"""
    await client.put("/profile", json=프로필, headers=인증)
    r = await client.post("/garments", json=의류, headers=인증)
    return 인증, r.json()["id"]


async def 다른계정(client):
    r = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True})
    return {"Authorization": f"Bearer {r.json()['token']}"}


class Test로그인_없이는_안_된다:
    async def test_분석에_토큰이_필요하다(self, client):
        assert (await client.post("/fittings", json={"garmentId": str(uuid.uuid4())})).status_code == 401


class Test분석_전에_갖춰야_할_것:
    async def test_프로필이_없으면_거절한다(self, client, 인증):
        r = await client.post("/garments", json=의류, headers=인증)
        분석 = await client.post("/fittings", json={"garmentId": r.json()["id"]}, headers=인증)
        assert 분석.status_code == 404
        assert 분석.json()["error"]["code"] == "PROFILE_NOT_FOUND"

    async def test_가슴이나_어깨_실측이_없으면_거절한다(self, client, 인증):
        # A4 추정기가 없다. 지어낸 값으로 리포트를 내지 않는다
        await client.put("/profile", json={"height": 175, "weight": 70, "gender": "남성"}, headers=인증)
        r = await client.post("/garments", json=의류, headers=인증)
        분석 = await client.post("/fittings", json={"garmentId": r.json()["id"]}, headers=인증)
        assert 분석.status_code == 400
        assert 분석.json()["error"]["code"] == "MEASUREMENTS_REQUIRED"

    async def test_없는_의류면_404(self, client, 인증):
        await client.put("/profile", json=프로필, headers=인증)
        r = await client.post("/fittings", json={"garmentId": str(uuid.uuid4())}, headers=인증)
        assert r.status_code == 404

    async def test_남의_의류는_분석할_수_없다(self, client, 준비):
        인증, 의류_id = 준비
        남 = await 다른계정(client)
        await client.put("/profile", json=프로필, headers=남)
        r = await client.post("/fittings", json={"garmentId": 의류_id}, headers=남)
        assert r.status_code == 404


class Test핏_분석:
    async def test_리포트를_돌려준다(self, client, 준비):
        인증, 의류_id = 준비
        r = await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)
        assert r.status_code == 201
        assert set(r.json()) == {"id", "garmentId", "report", "createdAt"}

    async def test_리포트가_계약_2_모양_그대로다(self, client, 준비):
        인증, 의류_id = 준비
        리포트 = (await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)).json()["report"]
        assert set(리포트) == {
            "fitGrade", "gaugeLevel", "chestEase", "waistEase", "shoulderDiff", "sleeveDiff",
            "lengthLabel", "sleeveLabel", "confidence", "preferredGrade", "gradeDistance",
            "showPreferenceCta",
        }

    async def test_계산이_맞는다(self, client, 준비):
        인증, 의류_id = 준비
        리포트 = (await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)).json()["report"]
        assert 리포트["chestEase"] == 10          # 51*2 − 92
        assert 리포트["fitGrade"] == "레귤러핏"
        assert 리포트["gradeDistance"] == 0        # 선호와 같다

    async def test_실측_배지가_붙는다(self, client, 준비):
        인증, 의류_id = 준비
        리포트 = (await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)).json()["report"]
        assert 리포트["confidence"] == "실측"


class Test조회:
    async def test_저장된_리포트를_다시_읽는다(self, client, 준비):
        인증, 의류_id = 준비
        만든것 = (await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)).json()
        r = await client.get(f"/fittings/{만든것['id']}", headers=인증)
        assert r.status_code == 200
        assert r.json()["report"] == 만든것["report"]

    async def test_리포트는_그때의_스냅샷이다(self, client, 준비):
        # 프로필이 나중에 바뀌어도 이미 만든 판정은 그대로여야 한다 (히스토리)
        인증, 의류_id = 준비
        만든것 = (await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)).json()
        await client.put("/profile", json=프로필 | {"chest": 70.0}, headers=인증)
        다시 = (await client.get(f"/fittings/{만든것['id']}", headers=인증)).json()
        assert 다시["report"]["chestEase"] == 10   # 바뀐 프로필로 다시 계산하면 32 다

    async def test_남의_리포트는_안_보인다(self, client, 준비):
        인증, 의류_id = 준비
        만든것 = (await client.post("/fittings", json={"garmentId": 의류_id}, headers=인증)).json()
        남 = await 다른계정(client)
        assert (await client.get(f"/fittings/{만든것['id']}", headers=남)).status_code == 404


class TestF10_사이즈_비교:
    """심사 시연에서 M·L 게이지를 나란히 놓는 화면"""

    @pytest.fixture
    async def 두사이즈(self, client, 준비):
        인증, M = 준비
        L = (await client.post("/garments", json=의류 | {"sizeName": "L", "chestWidth": 55.0},
                               headers=인증)).json()["id"]
        return 인증, [M, L]

    async def test_두_사이즈가_한_응답에_온다(self, client, 두사이즈):
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": ids}, headers=인증)
        assert r.status_code == 200
        assert set(r.json()) == {"sizes", "recommendedSize"}
        assert [s["sizeName"] for s in r.json()["sizes"]] == ["M", "L"]

    async def test_보낸_순서를_지킨다(self, client, 두사이즈):
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": list(reversed(ids))}, headers=인증)
        assert [s["sizeName"] for s in r.json()["sizes"]] == ["L", "M"]

    async def test_선호에_가까운_쪽을_추천한다(self, client, 두사이즈):
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": ids}, headers=인증)
        assert r.json()["recommendedSize"] == "M"     # 레귤러핏 선호 · M 이 레귤러핏

    async def test_각_리포트가_계약_2_그대로다(self, client, 두사이즈):
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": ids}, headers=인증)
        assert r.json()["sizes"][1]["report"]["fitGrade"] == "세미오버핏"

    async def test_비교는_저장하지_않는다(self, client, 두사이즈):
        # 계산을 두 번 돌리는 게 전부다. 히스토리를 어지럽히지 않는다
        인증, ids = 두사이즈
        await client.post("/fittings/compare", json={"garmentIds": ids}, headers=인증)
        만든것 = await client.post("/fittings", json={"garmentId": ids[0]}, headers=인증)
        assert 만든것.status_code == 201

    async def test_남의_의류가_섞이면_거절한다(self, client, 두사이즈):
        인증, ids = 두사이즈
        남 = await 다른계정(client)
        await client.put("/profile", json=프로필, headers=남)
        남의옷 = (await client.post("/garments", json=의류, headers=남)).json()["id"]
        r = await client.post("/fittings/compare", json={"garmentIds": [ids[0], 남의옷]}, headers=인증)
        assert r.status_code == 404

    async def test_사이즈_하나만_보내도_된다(self, client, 두사이즈):
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": ids[:1]}, headers=인증)
        assert len(r.json()["sizes"]) == 1

    async def test_사이즈명이_겹치면_합치지_않고_알려준다(self, client, 두사이즈):
        # dict 로 모으면 같은 사이즈명이 조용히 하나로 합쳐진다
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": [ids[0], ids[0]]}, headers=인증)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "DUPLICATE_SIZE_NAME"

    async def test_빈_목록은_거부한다(self, client, 두사이즈):
        인증, _ = 두사이즈
        assert (await client.post("/fittings/compare", json={"garmentIds": []}, headers=인증)).status_code == 422

    async def test_compare가_id_경로보다_먼저_잡힌다(self, client, 두사이즈):
        # /fittings/{id} 가 먼저 선언돼 있으면 compare 를 id 로 읽어 422 가 난다
        인증, ids = 두사이즈
        r = await client.post("/fittings/compare", json={"garmentIds": ids}, headers=인증)
        assert r.status_code == 200

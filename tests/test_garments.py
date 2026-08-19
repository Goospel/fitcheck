"""B3 · 의류 등록 API

필수 3치수(어깨너비·가슴단면·총장) + 선택 3개(소매길이·허리단면·신축성).
**한 행이 한 사이즈다** — 같은 옷의 M·L 은 두 번 등록하고, F-10 이 둘을 나란히 놓는다.

⚠️ 사진 업로드(D1)는 아직 없다. `photoPath` 는 받아만 두고 만들지 않는다.
"""

import pytest

옷 = {
    "kind": "티셔츠", "sizeName": "M",
    "shoulder": 48.0, "chestWidth": 55.0, "length": 70.0,
}


@pytest.fixture
async def 인증(client):
    r = await client.post("/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def 등록(client, 인증, **over):
    return await client.post("/garments", json=옷 | over, headers=인증)


class Test로그인_없이는_안_된다:
    async def test_등록에_토큰이_필요하다(self, client):
        assert (await client.post("/garments", json=옷)).status_code == 401

    async def test_목록에도_토큰이_필요하다(self, client):
        assert (await client.get("/garments")).status_code == 401


class Test등록:
    async def test_등록하면_id를_준다(self, client, 인증):
        r = await 등록(client, 인증)
        assert r.status_code == 201
        assert r.json()["id"]

    async def test_보낸_치수가_그대로_돌아온다(self, client, 인증):
        본문 = (await 등록(client, 인증)).json()
        assert (본문["shoulder"], 본문["chestWidth"], 본문["length"]) == (48.0, 55.0, 70.0)

    async def test_선택_치수를_안_보내면_null이다(self, client, 인증):
        본문 = (await 등록(client, 인증)).json()
        assert (본문["sleeve"], 본문["waistWidth"], 본문["stretch"]) == (None, None, None)

    async def test_선택_치수도_받는다(self, client, 인증):
        본문 = (await 등록(client, 인증, sleeve=60.0, waistWidth=52.0, stretch="약간")).json()
        assert (본문["sleeve"], 본문["waistWidth"], 본문["stretch"]) == (60.0, 52.0, "약간")

    @pytest.mark.parametrize("빠진것", ["kind", "sizeName", "shoulder", "chestWidth", "length"])
    async def test_필수가_빠지면_거부한다(self, client, 인증, 빠진것):
        assert (await client.post("/garments", json={k: v for k, v in 옷.items() if k != 빠진것},
                                  headers=인증)).status_code == 422

    async def test_사진은_아직_없어도_된다(self, client, 인증):
        # D1(업로드)이 나오기 전까지 B3 가 막히지 않게 열어 뒀다
        assert (await 등록(client, 인증)).json()["photoPath"] is None


class Test확정_상수를_지킨다:
    @pytest.mark.parametrize("종류", ["티셔츠", "셔츠", "니트", "후디", "맨투맨"])
    async def test_상의_5종은_받는다(self, client, 인증, 종류):
        assert (await 등록(client, 인증, kind=종류)).status_code == 201

    @pytest.mark.parametrize("종류", ["바지", "티셔츠 ", "아우터"])
    async def test_목록_밖의_종류는_거부한다(self, client, 인증, 종류):
        assert (await 등록(client, 인증, kind=종류)).status_code == 422

    @pytest.mark.parametrize("신축성", ["좋음", "약간", "없음"])
    async def test_신축성_3종은_받는다(self, client, 인증, 신축성):
        assert (await 등록(client, 인증, stretch=신축성)).status_code == 201

    async def test_목록_밖의_신축성은_거부한다(self, client, 인증):
        # 「보통」처럼 그럴듯한 값을 받으면 보정이 조용히 0 이 된다
        assert (await 등록(client, 인증, stretch="보통")).status_code == 422

    async def test_신축성_문구는_fit_grade에서_온다(self):
        from api.garments import STRETCH_LEVELS
        from fit.grade import STRETCH_RELIEF

        assert set(STRETCH_LEVELS) == set(STRETCH_RELIEF)


class Test치수_검증:
    @pytest.mark.parametrize("필드", ["shoulder", "chestWidth", "length"])
    async def test_0이하는_거부한다(self, client, 인증, 필드):
        assert (await 등록(client, 인증, **{필드: 0})).status_code == 422

    async def test_음수도_거부한다(self, client, 인증):
        assert (await 등록(client, 인증, chestWidth=-5)).status_code == 422

    async def test_사이즈명은_자유_문자열이다(self, client, 인증):
        # "M" 도 "95" 도 "FREE" 도 온다
        for 이름 in ["M", "95", "FREE"]:
            assert (await 등록(client, 인증, sizeName=이름)).status_code == 201

    async def test_빈_사이즈명은_거부한다(self, client, 인증):
        assert (await 등록(client, 인증, sizeName="")).status_code == 422


class Test목록:
    async def test_등록한_것이_나온다(self, client, 인증):
        await 등록(client, 인증)
        목록 = (await client.get("/garments", headers=인증)).json()
        assert len(목록) == 1
        assert 목록[0]["sizeName"] == "M"

    async def test_같은_옷의_두_사이즈가_따로_들어간다(self, client, 인증):
        # F-10 은 이 두 행을 골라 나란히 놓는다
        await 등록(client, 인증, sizeName="M", chestWidth=51.0)
        await 등록(client, 인증, sizeName="L", chestWidth=55.0)
        목록 = (await client.get("/garments", headers=인증)).json()
        assert {g["sizeName"] for g in 목록} == {"M", "L"}

    async def test_최신이_위로_온다(self, client, 인증):
        await 등록(client, 인증, sizeName="먼저")
        await 등록(client, 인증, sizeName="나중")
        assert (await client.get("/garments", headers=인증)).json()[0]["sizeName"] == "나중"

    async def test_남의_옷은_안_보인다(self, client, 인증):
        await 등록(client, 인증)
        남 = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True})
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        assert (await client.get("/garments", headers=헤더)).json() == []

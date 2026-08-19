"""B2 · 프로필 API

1단계 필수 3개(키·몸무게·성별) + 2단계 선택(실측 4개 · 선호 핏).
정확도는 `n/5` — 실측 4개 + 선호 핏 1개 (CLAUDE.md 1절).

⚠️ **치수가 비어 있으면 「추정」이다.** A4 추정기가 아직 없어 값은 `null` 이지만
   출처 자리는 지금부터 응답에 있다 — 프론트가 표시를 나눌 수 있어야 한다.
"""

import pytest

기본 = {"height": 175, "weight": 70, "gender": "남성"}
실측 = {"shoulder": 44.0, "chest": 92.0, "waist": 80.0, "arm": 58.0}


@pytest.fixture
async def 인증(client):
    r = await client.post("/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def 저장(client, 인증, **over):
    return await client.put("/profile", json=기본 | over, headers=인증)


class Test로그인_없이는_안_된다:
    async def test_조회에_토큰이_필요하다(self, client):
        assert (await client.get("/profile")).status_code == 401

    async def test_저장에도_토큰이_필요하다(self, client):
        assert (await client.put("/profile", json=기본)).status_code == 401


class Test1단계_필수_3개:
    async def test_저장하면_그대로_돌아온다(self, client, 인증):
        r = await 저장(client, 인증)
        assert r.status_code == 200
        assert (r.json()["height"], r.json()["weight"], r.json()["gender"]) == (175, 70, "남성")

    async def test_저장한_뒤_다시_조회해도_같다(self, client, 인증):
        await 저장(client, 인증)
        assert (await client.get("/profile", headers=인증)).json()["height"] == 175

    async def test_아직_안_만들었으면_404(self, client, 인증):
        r = await client.get("/profile", headers=인증)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "PROFILE_NOT_FOUND"

    async def test_다시_저장하면_덮어쓴다(self, client, 인증):
        await 저장(client, 인증)
        assert (await 저장(client, 인증, height=180)).json()["height"] == 180

    @pytest.mark.parametrize("빠진것", ["height", "weight", "gender"])
    async def test_하나라도_빠지면_거부한다(self, client, 인증, 빠진것):
        몸 = {k: v for k, v in 기본.items() if k != 빠진것}
        assert (await client.put("/profile", json=몸, headers=인증)).status_code == 422


class Test확정_상수를_지킨다:
    """CLAUDE.md 1절 — 키 100~220 · 몸무게 30~200 (정수)"""

    @pytest.mark.parametrize("키", [99, 221])
    async def test_키가_범위를_벗어나면_거부(self, client, 인증, 키):
        assert (await 저장(client, 인증, height=키)).status_code == 422

    @pytest.mark.parametrize("키", [100, 220])
    async def test_경계값은_받는다(self, client, 인증, 키):
        assert (await 저장(client, 인증, height=키)).status_code == 200

    @pytest.mark.parametrize("몸무게", [29, 201])
    async def test_몸무게가_범위를_벗어나면_거부(self, client, 인증, 몸무게):
        assert (await 저장(client, 인증, weight=몸무게)).status_code == 422

    @pytest.mark.parametrize("몸무게", [30, 200])
    async def test_몸무게_경계값은_받는다(self, client, 인증, 몸무게):
        assert (await 저장(client, 인증, weight=몸무게)).status_code == 200

    async def test_키는_정수만_받는다(self, client, 인증):
        assert (await 저장(client, 인증, height=175.5)).status_code == 422

    @pytest.mark.parametrize("성별", ["남성", "여성", "밝히지 않음"])
    async def test_성별_3지선다(self, client, 인증, 성별):
        assert (await 저장(client, 인증, gender=성별)).status_code == 200

    async def test_목록에_없는_성별은_거부한다(self, client, 인증):
        assert (await 저장(client, 인증, gender="남")).status_code == 422


class Test밝히지_않음도_전부_쓸_수_있다:
    """화면 설계서 — 성별을 안 밝혀도 모든 기능은 그대로다"""

    async def test_저장된다(self, client, 인증):
        assert (await 저장(client, 인증, gender="밝히지 않음")).status_code == 200

    async def test_정확도도_똑같이_계산된다(self, client, 인증):
        r = await 저장(client, 인증, gender="밝히지 않음", **실측, preferredGrade="레귤러핏")
        assert r.json()["accuracy"] == 5


class Test치수는_값과_출처를_같이_보낸다:
    """CLAUDE.md 6절 — 프론트가 이걸로 표시를 구분한다"""

    async def test_입력한_치수는_실측이다(self, client, 인증):
        r = await 저장(client, 인증, shoulder=44.0)
        assert r.json()["measurements"]["shoulder"] == {"value": 44.0, "source": "실측"}

    async def test_안_넣은_치수는_추정이다(self, client, 인증):
        # A4 가 아직 없어 value 는 null 이지만 자리는 지금부터 있다 (Q3)
        r = await 저장(client, 인증)
        assert r.json()["measurements"]["chest"] == {"value": None, "source": "추정"}

    async def test_네_치수가_전부_나온다(self, client, 인증):
        r = await 저장(client, 인증)
        assert set(r.json()["measurements"]) == {"shoulder", "chest", "waist", "arm"}

    async def test_치수를_지우면_다시_추정으로_돌아간다(self, client, 인증):
        await 저장(client, 인증, shoulder=44.0)
        r = await 저장(client, 인증)
        assert r.json()["measurements"]["shoulder"]["source"] == "추정"

    async def test_음수_치수는_거부한다(self, client, 인증):
        assert (await 저장(client, 인증, shoulder=-1)).status_code == 422


class Test정확도는_5점_만점:
    """실측 4개 + 선호 핏 1개 = 5"""

    async def test_필수만_넣으면_0(self, client, 인증):
        assert (await 저장(client, 인증)).json()["accuracy"] == 0

    async def test_실측_하나마다_1점(self, client, 인증):
        r = await 저장(client, 인증, shoulder=44.0, chest=92.0)
        assert r.json()["accuracy"] == 2

    async def test_선호_핏도_1점(self, client, 인증):
        assert (await 저장(client, 인증, preferredGrade="레귤러핏")).json()["accuracy"] == 1

    async def test_전부_채우면_5점(self, client, 인증):
        r = await 저장(client, 인증, **실측, preferredGrade="레귤러핏")
        assert r.json()["accuracy"] == 5


class Test선호_핏은_등급_목록에서만:
    async def test_선택_가능한_4종은_받는다(self, client, 인증):
        from fit.grade import PREFERRED_GRADES

        for 등급 in PREFERRED_GRADES:
            assert (await 저장(client, 인증, preferredGrade=등급)).status_code == 200

    async def test_너무_작음은_선호_핏이_아니다(self, client, 인증):
        # PRD 7.2 — 선택지는 슬림/레귤러/세미오버/오버 4개다. 경고를 선호할 사람은 없다
        assert (await 저장(client, 인증, preferredGrade="너무 작음")).status_code == 422

    async def test_목록에_없는_문구는_거부한다(self, client, 인증):
        assert (await 저장(client, 인증, preferredGrade="아무거나핏")).status_code == 422


class Test남의_프로필은_보이지_않는다:
    async def test_계정마다_따로다(self, client, 인증):
        await 저장(client, 인증, height=175)
        다른사람 = await client.post(
            "/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True}
        )
        헤더 = {"Authorization": f"Bearer {다른사람.json()['token']}"}
        assert (await client.get("/profile", headers=헤더)).status_code == 404

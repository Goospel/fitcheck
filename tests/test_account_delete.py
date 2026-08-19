"""C5 · 계정 삭제

삭제하면 프로필·의류·피팅 결과·이메일이 **전부 즉시** 사라진다.

⚠️ 로그아웃 엔드포인트는 만들지 않는다 — JWT 는 서버에 상태가 없어서 「로그아웃」이
   할 일이 없다. 프론트가 토큰을 버리면 끝이다 (docs/contracts.md 부록).
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Fitting, Garment, Profile, User

의류 = {"kind": "티셔츠", "sizeName": "M", "shoulder": 48.0, "chestWidth": 51.0, "length": 70.0}
프로필 = {
    "height": 175, "weight": 70, "gender": "남성",
    "shoulder": 44.0, "chest": 92.0, "waist": 80.0, "arm": 58.0, "preferredGrade": "레귤러핏",
}


async def 가입(client, email="a@b.com"):
    r = await client.post("/auth/signup", json={"email": email, "password": "hunter22", "isOver14": True})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
async def 가득찬계정(client):
    """프로필 · 의류 · 피팅까지 다 만들어 둔 계정"""
    인증 = await 가입(client)
    await client.put("/profile", json=프로필, headers=인증)
    옷 = (await client.post("/garments", json=의류, headers=인증)).json()["id"]
    await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
    return 인증


async def 행수(engine, model) -> int:
    async with AsyncSession(engine) as s:
        return await s.scalar(select(func.count()).select_from(model))


class TestSQLite가_외래키를_지키는지:
    """⚠️ SQLite 는 외래키를 **기본적으로 안 지킨다.** 켜지 않으면 아래 CASCADE
    테스트가 전부 헛돌고, 「지워진다」는 확인이 거짓이 된다."""

    async def test_외래키_강제가_켜져_있다(self, db_engine):
        from sqlalchemy import text

        async with db_engine.begin() as conn:
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1


class Test계정_삭제:
    async def test_토큰이_필요하다(self, client):
        assert (await client.delete("/auth/me")).status_code == 401

    async def test_삭제하면_204다(self, client, 가득찬계정):
        assert (await client.delete("/auth/me", headers=가득찬계정)).status_code == 204

    async def test_삭제한_계정의_토큰은_안_통한다(self, client, 가득찬계정):
        await client.delete("/auth/me", headers=가득찬계정)
        assert (await client.get("/auth/me", headers=가득찬계정)).status_code == 401

    async def test_이메일이_사라진다(self, client, 가득찬계정):
        await client.delete("/auth/me", headers=가득찬계정)
        assert (await client.post("/auth/check", json={"email": "a@b.com"})).json() == {"exists": False}

    async def test_같은_이메일로_다시_가입할_수_있다(self, client, 가득찬계정):
        await client.delete("/auth/me", headers=가득찬계정)
        r = await client.post("/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True})
        assert r.status_code == 201


class Test딸린_것도_같이_지워진다:
    """PRD — 삭제 시 프로필·사진·피팅 결과·이메일 전부 즉시 삭제"""

    async def test_지우기_전에는_다_있다(self, client, 가득찬계정, db_engine):
        assert (await 행수(db_engine, Profile), await 행수(db_engine, Garment),
                await 행수(db_engine, Fitting)) == (1, 1, 1)

    @pytest.mark.parametrize("모델", [Profile, Garment, Fitting, User])
    async def test_지우면_아무것도_안_남는다(self, client, 가득찬계정, db_engine, 모델):
        await client.delete("/auth/me", headers=가득찬계정)
        assert await 행수(db_engine, 모델) == 0

    async def test_남의_데이터는_그대로다(self, client, 가득찬계정, db_engine):
        남 = await 가입(client, "c@d.com")
        await client.put("/profile", json=프로필, headers=남)
        await client.delete("/auth/me", headers=가득찬계정)
        assert await 행수(db_engine, Profile) == 1
        assert (await client.get("/profile", headers=남)).status_code == 200

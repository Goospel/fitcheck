"""C1 · 가입 · 로그인

프론트 로그인 화면 4단계가 `POST /auth/check` 응답 하나에 걸려 있다 (plan.md C1).
"""

import uuid
from datetime import timedelta

import jwt
import pytest

from auth.security import create_token, decode_token, hash_password, verify_password
from core.config import settings
from core.errors import AppError

가입 = {"email": "a@b.com", "password": "hunter22", "isOver14": True}


async def 가입시키기(client, **over):
    return await client.post("/auth/signup", json=가입 | over)


class Test비밀번호는_평문으로_남지_않는다:
    def test_해시에_평문이_들어_있지_않다(self):
        assert "hunter22" not in hash_password("hunter22")

    def test_같은_비밀번호도_매번_다른_해시다(self):
        # 솔트가 없으면 같은 비밀번호끼리 서로를 드러낸다
        assert hash_password("hunter22") != hash_password("hunter22")

    def test_맞는_비밀번호는_통과한다(self):
        assert verify_password("hunter22", hash_password("hunter22")) is True

    def test_틀린_비밀번호는_막힌다(self):
        assert verify_password("hunter23", hash_password("hunter22")) is False

    def test_해시가_망가져_있어도_터지지_않는다(self):
        # DB 가 오염돼도 500 대신 「비밀번호가 다르다」로 떨어져야 한다
        assert verify_password("hunter22", "이건해시가아니다") is False


class Test72바이트_함정:
    """bcrypt 5.0 은 72바이트를 넘기면 **예외를 던진다.** 한글은 3바이트라
    24자면 도달한다 — 안 막으면 긴 비밀번호를 넣은 사용자가 500 을 본다."""

    def test_한글_24자가_이미_72바이트다(self):
        assert len(("가" * 24).encode()) == 72

    def test_넘으면_500이_아니라_400이다(self):
        with pytest.raises(AppError) as e:
            hash_password("가" * 25)
        assert e.value.status_code == 400

    def test_72바이트까지는_받는다(self):
        assert verify_password("가" * 24, hash_password("가" * 24)) is True


class Test토큰:
    def test_왕복한다(self):
        누구 = uuid.uuid4()
        assert decode_token(create_token(누구)) == 누구

    def test_위조된_토큰은_거부한다(self):
        가짜 = jwt.encode({"sub": str(uuid.uuid4())}, "다른비밀", algorithm="HS256")
        with pytest.raises(AppError) as e:
            decode_token(가짜)
        assert e.value.status_code == 401

    def test_만료된_토큰은_거부한다(self):
        from datetime import datetime, timezone

        지난것 = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.jwt_secret,
            algorithm="HS256",
        )
        with pytest.raises(AppError) as e:
            decode_token(지난것)
        assert e.value.status_code == 401

    def test_아무_문자열이나_넣어도_터지지_않는다(self):
        with pytest.raises(AppError):
            decode_token("어쩌구저쩌구")


class Test이메일_확인이_화면을_가른다:
    """PRD 는 가입/로그인 탭을 두지 않는다 — 서버가 판단해 분기한다"""

    async def test_없는_이메일이면_가입으로(self, client):
        r = await client.post("/auth/check", json={"email": "none@b.com"})
        assert r.status_code == 200
        assert r.json() == {"exists": False}

    async def test_있는_이메일이면_로그인으로(self, client):
        await 가입시키기(client)
        r = await client.post("/auth/check", json={"email": "a@b.com"})
        assert r.json() == {"exists": True}

    async def test_대소문자가_달라도_같은_계정이다(self, client):
        await 가입시키기(client)
        r = await client.post("/auth/check", json={"email": "A@B.com"})
        assert r.json() == {"exists": True}

    async def test_이메일_모양이_아니면_거부한다(self, client):
        r = await client.post("/auth/check", json={"email": "골뱅이없음"})
        assert r.status_code == 422


class Test가입:
    async def test_토큰을_바로_준다(self, client):
        # 가입 후 로그인을 또 시키지 않는다
        r = await 가입시키기(client)
        assert r.status_code == 201
        assert set(r.json()) == {"token", "userId"}

    async def test_받은_토큰이_바로_통한다(self, client):
        토큰 = (await 가입시키기(client)).json()["token"]
        assert decode_token(토큰)

    async def test_같은_이메일로_두_번_가입할_수_없다(self, client):
        await 가입시키기(client)
        r = await 가입시키기(client)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "EMAIL_TAKEN"

    async def test_대소문자만_다른_이메일도_중복이다(self, client):
        await 가입시키기(client)
        r = await 가입시키기(client, email="A@B.COM")
        assert r.status_code == 409

    async def test_만_14세_미만은_가입할_수_없다(self, client):
        r = await 가입시키기(client, isOver14=False)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "AGE_RESTRICTED"

    async def test_나이_확인을_빠뜨리면_거부한다(self, client):
        r = await client.post("/auth/signup", json={"email": "c@d.com", "password": "hunter22"})
        assert r.status_code == 422

    async def test_짧은_비밀번호는_거부한다(self, client):
        r = await 가입시키기(client, password="1234")
        assert r.status_code == 422

    async def test_응답에_비밀번호가_없다(self, client):
        본문 = (await 가입시키기(client)).text
        assert "hunter22" not in 본문


class Test로그인:
    async def test_맞으면_토큰을_준다(self, client):
        await 가입시키기(client)
        r = await client.post("/auth/login", json={"email": "a@b.com", "password": "hunter22"})
        assert r.status_code == 200
        assert set(r.json()) == {"token", "userId"}

    async def test_가입_때와_같은_계정이다(self, client):
        가입한_id = (await 가입시키기(client)).json()["userId"]
        r = await client.post("/auth/login", json={"email": "a@b.com", "password": "hunter22"})
        assert r.json()["userId"] == 가입한_id

    async def test_비밀번호가_틀리면_401(self, client):
        await 가입시키기(client)
        r = await client.post("/auth/login", json={"email": "a@b.com", "password": "틀린비밀번호"})
        assert r.status_code == 401

    async def test_없는_계정도_같은_응답이다(self, client):
        # 로그인 단계에서 계정 존재 여부를 추가로 흘리지 않는다
        r = await client.post("/auth/login", json={"email": "none@b.com", "password": "hunter22"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


class Test인증이_필요한_요청:
    async def test_토큰이_없으면_401(self, client):
        r = await client.get("/auth/me")
        assert r.status_code == 401

    async def test_토큰이_있으면_내_정보가_나온다(self, client):
        가입응답 = (await 가입시키기(client)).json()
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {가입응답['token']}"})
        assert r.status_code == 200
        assert r.json() == {"userId": 가입응답["userId"], "email": "a@b.com"}

    @pytest.mark.parametrize("가짜", ["abc", "a.b.c", "Bearer", ""])
    async def test_엉뚱한_토큰이면_401(self, client, 가짜):
        # HTTP 헤더는 ASCII 만 담는다 — 한글 토큰은 전송 자체가 안 되므로 여기 대상이 아니다
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {가짜}"})
        assert r.status_code == 401

    async def test_지워진_계정의_토큰은_통하지_않는다(self, client, db_engine):
        from sqlalchemy import delete
        from sqlalchemy.ext.asyncio import AsyncSession

        토큰 = (await 가입시키기(client)).json()["token"]
        async with AsyncSession(db_engine) as s:
            from db.models import User

            await s.execute(delete(User))
            await s.commit()
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {토큰}"})
        assert r.status_code == 401


class Test에러_규격을_지킨다:
    """core/errors.py — 세 명의 API 가 같은 모양을 낸다"""

    async def test_에러가_error_객체로_나온다(self, client):
        r = await client.post("/auth/login", json={"email": "a@b.com", "password": "hunter22"})
        assert set(r.json()) == {"error"}
        assert set(r.json()["error"]) == {"code", "message"}


class TestPRD_비밀번호_규칙:
    """PRD 7.8 — 8자 이상, 영문·숫자·기호 중 2종 이상 조합"""

    @pytest.mark.parametrize("비번", ["hunter22", "hunter!!", "1234567!", "패스워드입니다1"])
    async def test_2종_이상_섞이면_통과한다(self, client, 비번):
        r = await client.post("/auth/signup",
                              json={"email": "z@b.com", "password": 비번, "isOver14": True})
        assert r.status_code == 201

    @pytest.mark.parametrize("비번", ["abcdefgh", "12345678", "!!!!!!!!", "비밀번호비밀번호"])
    async def test_1종뿐이면_거부한다(self, client, 비번):
        r = await client.post("/auth/signup",
                              json={"email": "z@b.com", "password": 비번, "isOver14": True})
        assert r.status_code == 422

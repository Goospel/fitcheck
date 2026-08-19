"""D4 · 이미지 생성 큐 — `api/fittings.py` 의 잡 생성 분기 + `jobs/worker.py`

⚠️ 진짜 OpenAI 를 부르지 않는다 — `images.generate.generate_tryon` 을 가짜로 바꾼다.
   사진은 `images/validate.py` 의 해상도 검증(512×768)을 거칠 필요가 없는 부분만
   보므로, 업로드 API 대신 `test_dedup.py` 의 관행대로 DB 행에 `photo_path` 를
   직접 심는다.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import Fitting, Garment, ImageJob, Profile, User
from jobs import worker

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
async def 준비(client, 인증, db_engine):
    await client.put("/profile", json=프로필, headers=인증)
    옷 = (await client.post("/garments", json=의류, headers=인증)).json()["id"]
    async with AsyncSession(db_engine) as s:
        user_id = (await s.execute(select(User.id).where(User.email == "a@b.com"))).scalar_one()
    return 인증, 옷, user_id


async def _사진_달기(engine, user_id: uuid.UUID, garment_id: str) -> None:
    """업로드 API 를 거치지 않고 사진 경로만 직접 심는다 — 여기서 보려는 것은
    D2(해상도 검증)가 아니라 D4(잡 생성·큐 처리)다."""
    async with AsyncSession(engine) as s:
        (await s.get(Profile, user_id)).photo_path = f"{user_id}/profile.jpg"
        (await s.get(Garment, uuid.UUID(garment_id))).photo_path = f"{user_id}/garment-{garment_id}.jpg"
        await s.commit()


class Test사진이_다_있어야_잡을_만든다:
    async def test_사진_없으면_리포트만(self, client, 준비):
        인증, 옷, _ = 준비
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.json()["status"] == "리포트만"

    async def test_사진_둘_다_있으면_대기_잡이_생긴다(self, client, 준비, db_engine):
        인증, 옷, user_id = 준비
        await _사진_달기(db_engine, user_id, 옷)
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.json()["status"] == "대기"
        async with AsyncSession(db_engine) as s:
            jobs = (await s.execute(select(ImageJob))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].fitting_id == uuid.UUID(r.json()["id"])

    async def test_한쪽만_있으면_리포트만(self, client, 준비, db_engine):
        인증, 옷, user_id = 준비
        async with AsyncSession(db_engine) as s:
            (await s.get(Profile, user_id)).photo_path = f"{user_id}/profile.jpg"
            await s.commit()
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.json()["status"] == "리포트만"


class Test큐_집기:
    async def test_대기가_없으면_None(self, db_engine):
        async with AsyncSession(db_engine) as s:
            assert await worker.claim_next(s) is None

    async def test_오래_기다린_것부터_집는다(self, client, 준비, db_engine):
        인증, 옷, user_id = 준비
        await _사진_달기(db_engine, user_id, 옷)
        # 같은 의류 재요청은 D6 재사용에 걸리므로 사이즈가 다른 두 번째 의류로 잡을 하나 더 만든다
        L = (await client.post("/garments", json=의류 | {"sizeName": "L", "chestWidth": 55.0},
                               headers=인증)).json()["id"]
        async with AsyncSession(db_engine) as s:
            (await s.get(Garment, uuid.UUID(L))).photo_path = f"{user_id}/garment-{L}.jpg"
            await s.commit()

        첫째 = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        둘째 = (await client.post("/fittings", json={"garmentId": L}, headers=인증)).json()

        async with AsyncSession(db_engine) as s:
            job = await worker.claim_next(s)
        assert job.fitting_id == uuid.UUID(첫째["id"])
        assert job.status == "생성중"
        assert job.attempts == 1

        async with AsyncSession(db_engine) as s:
            둘째_잡 = (await s.execute(
                select(ImageJob).where(ImageJob.fitting_id == uuid.UUID(둘째["id"]))
            )).scalar_one()
        assert 둘째_잡.status == "대기"     # 아직 안 집혔다


class Test잡_처리:
    async def test_성공하면_완료_상태와_이미지_경로가_남는다(self, client, 준비, db_engine, monkeypatch):
        인증, 옷, user_id = 준비
        await _사진_달기(db_engine, user_id, 옷)
        fitting = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()

        async def 가짜_생성(prompt, person, garment):
            return b"fake-png-bytes"

        monkeypatch.setattr(worker.generate, "generate_tryon", 가짜_생성)

        async with AsyncSession(db_engine) as s:
            job = await worker.claim_next(s)
            await worker.process(s, job)

        async with AsyncSession(db_engine) as s:
            f = await s.get(Fitting, uuid.UUID(fitting["id"]))
            j = await s.get(ImageJob, job.id)
        assert j.status == "완료"
        assert f.image_path == f"{user_id}/result-{fitting['id']}.png"

    async def test_실패하면_재시도로_대기로_돌아간다(self, client, 준비, db_engine, monkeypatch):
        인증, 옷, user_id = 준비
        await _사진_달기(db_engine, user_id, 옷)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)

        async def 터짐(prompt, person, garment):
            raise RuntimeError("모델 호출 실패")

        monkeypatch.setattr(worker.generate, "generate_tryon", 터짐)

        async with AsyncSession(db_engine) as s:
            job = await worker.claim_next(s)
            await worker.process(s, job)
            j = await s.get(ImageJob, job.id)
        assert j.status == "대기"          # attempts(1) < MAX_ATTEMPTS
        assert j.error

    async def test_MAX_ATTEMPTS_넘으면_실패로_굳는다(self, client, 준비, db_engine, monkeypatch):
        인증, 옷, user_id = 준비
        await _사진_달기(db_engine, user_id, 옷)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)

        async def 터짐(prompt, person, garment):
            raise RuntimeError("모델 호출 실패")

        monkeypatch.setattr(worker.generate, "generate_tryon", 터짐)

        job = None
        for _ in range(worker.MAX_ATTEMPTS):
            async with AsyncSession(db_engine) as s:
                job = await worker.claim_next(s)
                await worker.process(s, job)

        async with AsyncSession(db_engine) as s:
            j = await s.get(ImageJob, job.id)
        assert j.status == "실패"


class Test고아_잡_복구:
    async def test_생성중이던_잡을_대기로_되돌린다(self, client, 준비, db_engine, monkeypatch):
        인증, 옷, _ = 준비
        fitting = (await client.post("/fittings", json={"garmentId": 옷}, headers=인증)).json()
        async with AsyncSession(db_engine) as s:
            s.add(ImageJob(fitting_id=uuid.UUID(fitting["id"]), status="생성중"))
            await s.commit()

        # reset_orphaned_jobs 는 자기 세션을 직접 여는데, 그 세션은 운영 DB(엔진)를
        # 바라본다 — 테스트에서는 in-memory sqlite 를 바라보게 바꿔치기한다
        monkeypatch.setattr(
            worker, "_sessionmaker",
            lambda: async_sessionmaker(db_engine, expire_on_commit=False),
        )
        await worker.reset_orphaned_jobs()

        async with AsyncSession(db_engine) as s:
            j = (await s.execute(select(ImageJob))).scalar_one()
        assert j.status == "대기"

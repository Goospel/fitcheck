"""D4 · 비동기 잡 큐 + D5 · 타임아웃·실패 처리 (plan.md 6절)

생성이 2분 걸린다 (D0 실측 115초). 요청을 붙잡고 기다릴 수 없으니 큐에 넣고
워커가 가져간다 — **창을 닫거나 재접속해도 결과가 유실되지 않아야 한다.**

⚠️ **여기서 지켜야 할 것은 「빈손으로 돌아가지 않는다」다** (F-09 · PRD 7.5).
   생성이 실패해도 · 타임아웃이 나도 · 서버가 재배포로 죽어도 **핏 리포트는 남는다.**

⚠️ **SQLite 는 `FOR UPDATE SKIP LOCKED` 를 조용히 무시한다** (SQLAlchemy 가 빼고
   컴파일한다). 즉 **이 파일은 잠금을 검증하지 못한다** — 검증하는 것은 상태 전이와
   실패 경로이고, 잠금은 실제 Postgres 로 따로 쟀다 (스크래치패드 `d4_smoke.py`:
   동시 5건 중복 0 · 잠긴 행 앞에서 0.17초 vs 2.05초).
"""

import asyncio
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Fitting, ImageJob, Profile
from jobs import worker

의류 = {"kind": "티셔츠", "sizeName": "M", "shoulder": 48.0, "chestWidth": 51.0, "length": 70.0}
프로필 = {
    "height": 175, "weight": 70, "gender": "남성",
    "shoulder": 44.0, "chest": 92.0, "waist": 80.0, "arm": 58.0, "preferredGrade": "레귤러핏",
}


def 사진(w=512, h=768, fmt="JPEG", 색=(40, 90, 140)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), 색).save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def 생성기(monkeypatch):
    """가짜 이미지 생성. **테스트는 유료 API 를 부르지 않는다.**

    `호출` 에 넘어온 인자가 쌓이고, `터뜨리기` 로 실패를 만든다.
    """
    from images import generate

    상태 = {"호출": [], "예외": None, "지연": 0.0}

    async def 가짜(person: bytes, garment: bytes, prompt: str) -> bytes:
        상태["호출"].append({"person": person, "garment": garment, "prompt": prompt})
        if 상태["지연"]:
            await asyncio.sleep(상태["지연"])
        if 상태["예외"]:
            raise 상태["예외"]
        return 사진(1024, 1536, "PNG")

    monkeypatch.setattr(generate, "generate_image", 가짜)
    return 상태


@pytest.fixture
async def 인증(client):
    r = await client.post(
        "/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True}
    )
    헤더 = {"Authorization": f"Bearer {r.json()['token']}"}
    await client.put("/profile", json=프로필, headers=헤더)
    return 헤더


async def 옷_등록(client, 인증, 사진있음=True):
    옷 = (await client.post("/garments", json=의류, headers=인증)).json()["id"]
    if 사진있음:
        # 전신 사진과 **다른** 그림이어야 「두 장이 제대로 넘어갔나」를 잴 수 있다
        await client.put(f"/photos/garments/{옷}",
                         files={"file": ("g.jpg", 사진(색=(200, 30, 30)), "image/jpeg")},
                         headers=인증)
    return 옷


async def 전신사진(client, 인증):
    await client.put("/photos/profile", files={"file": ("p.jpg", 사진(), "image/jpeg")},
                     headers=인증)


class Test잡은_사진이_다_있을_때만_생긴다:
    """사진이 없으면 만들 그림이 없다. 없는 것을 「대기」로 두면 **영원히 안 끝나는 잡**이 목록에 남는다"""

    async def test_둘_다_있으면_큐에_들어간다(self, client, 인증):
        await 전신사진(client, 인증)
        옷 = await 옷_등록(client, 인증)
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.status_code == 201
        assert r.json()["status"] == "대기"

    async def test_전신사진이_없으면_리포트만(self, client, 인증):
        옷 = await 옷_등록(client, 인증)
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.json()["status"] == "리포트만"

    async def test_의류사진이_없으면_리포트만(self, client, 인증):
        await 전신사진(client, 인증)
        옷 = await 옷_등록(client, 인증, 사진있음=False)
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.json()["status"] == "리포트만"

    async def test_리포트만이어도_리포트는_나온다(self, client, 인증):
        # F-09 — 사진이 없다고 판정까지 못 받는 게 아니다
        옷 = await 옷_등록(client, 인증, 사진있음=False)
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.json()["report"]["fitGrade"] == "레귤러핏"


class Test집어가기:
    async def test_대기를_집으면_생성중이_된다(self, client, 인증, db_engine):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)

        async with AsyncSession(db_engine) as db:
            잡id = await worker._claim(db)
        assert 잡id is not None

        async with AsyncSession(db_engine) as db:
            뒤 = await db.get(ImageJob, 잡id)
            assert 뒤.status == "생성중"
            assert 뒤.started_at is not None
            assert 뒤.attempts == 1

    async def test_집을_게_없으면_None(self, db_engine):
        async with AsyncSession(db_engine) as db:
            assert await worker._claim(db) is None

    async def test_생성중인_것은_다시_안_집는다(self, client, 인증, db_engine):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        async with AsyncSession(db_engine) as db:
            assert await worker._claim(db) is not None
        async with AsyncSession(db_engine) as db:
            assert await worker._claim(db) is None      # 같은 것을 두 번 집지 않는다

    async def test_오래_기다린_것부터_집는다(self, client, 인증, db_engine):
        await 전신사진(client, 인증)
        첫옷, 둘옷 = await 옷_등록(client, 인증), await 옷_등록(client, 인증)
        첫 = (await client.post("/fittings", json={"garmentId": 첫옷}, headers=인증)).json()["id"]
        await client.post("/fittings", json={"garmentId": 둘옷}, headers=인증)

        async with AsyncSession(db_engine) as db:
            잡id = await worker._claim(db)
            assert str((await db.get(ImageJob, 잡id)).fitting_id) == 첫


class Test한_건_처리:
    async def test_성공하면_완료가_되고_이미지가_붙는다(self, client, 인증, db_engine, 생성기, 저장소):
        await 전신사진(client, 인증)
        피팅 = (await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)},
                                 headers=인증)).json()["id"]
        await worker.run_once(db_engine)

        r = (await client.get(f"/fittings/{피팅}", headers=인증)).json()
        assert r["status"] == "완료"
        assert r["imagePath"] in 저장소
        assert r["imageUrl"].startswith("https://")

    async def test_결과가_내_폴더에_들어간다(self, client, 인증, db_engine, 생성기, 저장소):
        # 계정을 지울 때 list 한 번으로 같이 걷혀야 한다 (D1 과 같은 규칙)
        await 전신사진(client, 인증)
        피팅 = (await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)},
                                 headers=인증)).json()["id"]
        await worker.run_once(db_engine)
        경로 = (await client.get(f"/fittings/{피팅}", headers=인증)).json()["imagePath"]
        assert 경로.endswith(f"fitting-{피팅}.png")
        assert 경로.split("/")[0] != ""       # 사용자 폴더 아래

    async def test_사진_두_장과_D3_프롬프트가_넘어간다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        await worker.run_once(db_engine)

        호출 = 생성기["호출"][0]
        assert 호출["person"] and 호출["garment"]
        assert 호출["person"] != 호출["garment"]          # 같은 사진을 두 번 넘기지 않는다
        assert "레귤러핏" not in 호출["prompt"]            # 모델에게는 영어만 간다
        assert "regular fit" in 호출["prompt"].lower()

    async def test_처리할_게_없으면_아무_일도_없다(self, db_engine, 생성기):
        await worker.run_once(db_engine)
        assert 생성기["호출"] == []

    async def test_계정을_지우면_결과_이미지도_사라진다(self, client, 인증, db_engine, 생성기, 저장소):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        await worker.run_once(db_engine)
        assert len(저장소) == 3          # 전신 + 의류 + 결과

        await client.delete("/auth/me", headers=인증)
        assert 저장소 == {}


class Test실패해도_리포트는_남는다:
    """F-09 · PRD 7.5 — 사용자가 빈손으로 돌아가지 않게"""

    async def test_생성이_터지면_다시_시도한다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        생성기["예외"] = RuntimeError("모델이 삐졌다")

        await worker.run_once(db_engine)
        async with AsyncSession(db_engine) as db:
            잡 = (await db.scalars(select(ImageJob))).one()
            assert 잡.status == "대기"        # 일시적 오류일 수 있다 — 한 번은 더 해 본다
            assert 잡.attempts == 1

    async def test_상한을_넘기면_실패로_굳는다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        피팅 = (await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)},
                                 headers=인증)).json()["id"]
        생성기["예외"] = RuntimeError("모델이 삐졌다")
        for _ in range(worker.MAX_ATTEMPTS):
            await worker.run_once(db_engine)

        r = (await client.get(f"/fittings/{피팅}", headers=인증)).json()
        assert r["status"] == "실패"
        assert r["imagePath"] is None
        assert r["report"]["fitGrade"] == "레귤러핏"      # ← 이게 이 절의 요점이다

    async def test_실패해도_영원히_돌지_않는다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        생성기["예외"] = RuntimeError("계속 터진다")
        for _ in range(worker.MAX_ATTEMPTS + 3):
            await worker.run_once(db_engine)
        assert len(생성기["호출"]) == worker.MAX_ATTEMPTS

    async def test_에러_문구를_사용자에게_보여주지_않는다(self, client, 인증, db_engine, 생성기):
        # 모델 응답에 키·내부 경로가 섞여 나올 수 있다
        await 전신사진(client, 인증)
        피팅 = (await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)},
                                 headers=인증)).json()["id"]
        생성기["예외"] = RuntimeError("sk-proj-비밀키가-섞인-메시지")
        for _ in range(worker.MAX_ATTEMPTS):
            await worker.run_once(db_engine)

        본문 = (await client.get(f"/fittings/{피팅}", headers=인증)).text
        assert "sk-proj" not in 본문

    async def test_타임아웃이_나면_실패로_간다(self, client, 인증, db_engine, 생성기, monkeypatch):
        monkeypatch.setattr(worker, "TIMEOUT_SECONDS", 0.05)
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        생성기["지연"] = 5.0

        for _ in range(worker.MAX_ATTEMPTS):
            await worker.run_once(db_engine)
        async with AsyncSession(db_engine) as db:
            assert (await db.scalars(select(ImageJob))).one().status == "실패"

    async def test_경로가_비어_있으면_모델을_안_부른다(self, client, 인증, db_engine, 생성기):
        """잡을 만들 때 사진을 확인하므로 **지금은 일어나지 않는 상태**다.

        ⚠️ 이 테스트는 `_재료` 의 가드를 **구분하지 못한다** — 가드를 지워도 빈 경로는
           `storage.download` 에서 터져 결과가 같다(동치 돌연변이, 실측). 여기서 재는
           것은 「사진 없이 유료 호출이 나가지 않는다」와 「실패로 끝난다」이고,
           그건 가드가 있든 없든 지켜져야 하는 성질이다.
        """
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        async with AsyncSession(db_engine) as db:
            프로필 = (await db.scalars(select(Profile))).one()
            프로필.photo_path = None
            await db.commit()

        for _ in range(worker.MAX_ATTEMPTS):
            await worker.run_once(db_engine)
        assert 생성기["호출"] == []              # 사진 없이 유료 호출을 하지 않는다
        async with AsyncSession(db_engine) as db:
            assert (await db.scalars(select(ImageJob))).one().status == "실패"

    async def test_사진이_사라졌으면_붙잡고_있지_않는다(self, client, 인증, db_engine, 생성기, 저장소):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        저장소.clear()                                   # 저장소에서 사진이 사라진 상황
        for _ in range(worker.MAX_ATTEMPTS):
            await worker.run_once(db_engine)
        async with AsyncSession(db_engine) as db:
            assert (await db.scalars(select(ImageJob))).one().status == "실패"


class Test재배포_좀비:
    """D5 — 서버가 죽으면 「생성중」이 영원히 남는다. 시작할 때 정리한다"""

    async def test_생성중은_다시_큐로_돌아간다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        async with AsyncSession(db_engine) as db:
            await worker._claim(db)                     # 집어간 채로 서버가 죽었다고 치자

        await worker.sweep_zombies(db_engine)
        async with AsyncSession(db_engine) as db:
            assert (await db.scalars(select(ImageJob))).one().status == "대기"

    async def test_시도를_다_쓴_좀비는_실패로_굳는다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        for _ in range(worker.MAX_ATTEMPTS):
            async with AsyncSession(db_engine) as db:
                잡 = await worker._claim(db)
            await worker.sweep_zombies(db_engine)

        async with AsyncSession(db_engine) as db:
            assert (await db.scalars(select(ImageJob))).one().status == "실패"

    async def test_대기와_완료는_안_건드린다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        첫옷, 둘옷 = await 옷_등록(client, 인증), await 옷_등록(client, 인증)
        await client.post("/fittings", json={"garmentId": 첫옷}, headers=인증)
        await client.post("/fittings", json={"garmentId": 둘옷}, headers=인증)
        await worker.run_once(db_engine)                # 하나는 완료

        await worker.sweep_zombies(db_engine)
        async with AsyncSession(db_engine) as db:
            상태 = sorted(j.status for j in (await db.scalars(select(ImageJob))).all())
        assert 상태 == ["대기", "완료"]


class Test결과를_다시_찾을_수_있다:
    """창을 닫아도 유실되지 않는다 — 히스토리(B5)가 유일한 경로다"""

    async def test_히스토리에_이미지_URL_이_붙는다(self, client, 인증, db_engine, 생성기, 저장소):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        await worker.run_once(db_engine)

        항목 = (await client.get("/fittings", headers=인증)).json()["items"][0]
        assert 항목["imageUrl"].startswith("https://")
        assert 항목["garment"]["photoUrl"].startswith("https://")   # D1 에서 미룬 것

    async def test_생성_전에는_URL_이_없다(self, client, 인증, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        항목 = (await client.get("/fittings", headers=인증)).json()["items"][0]
        assert 항목["imageUrl"] is None

    async def test_뱃지_개수가_상태를_따라간다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)}, headers=인증)
        assert (await client.get("/fittings", headers=인증)).json()["counts"]["대기"] == 1
        await worker.run_once(db_engine)
        개수 = (await client.get("/fittings", headers=인증)).json()["counts"]
        assert (개수["대기"], 개수["완료"]) == (0, 1)

    async def test_남의_결과는_안_보인다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        피팅 = (await client.post("/fittings", json={"garmentId": await 옷_등록(client, 인증)},
                                 headers=인증)).json()["id"]
        await worker.run_once(db_engine)
        남 = await client.post(
            "/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True}
        )
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        assert (await client.get(f"/fittings/{피팅}", headers=헤더)).status_code == 404


class Test중복_생성_방지가_계속_통한다:
    """D6 이 잡까지 막아야 한다 — 10분(실측 2분) + 유료 호출이 두 번 돌면 안 된다"""

    async def test_두_번_눌러도_잡은_하나다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        옷 = await 옷_등록(client, 인증)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        둘째 = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert 둘째.status_code == 200

        async with AsyncSession(db_engine) as db:
            assert len((await db.scalars(select(ImageJob))).all()) == 1

    async def test_완료된_것을_다시_생성하지_않는다(self, client, 인증, db_engine, 생성기):
        await 전신사진(client, 인증)
        옷 = await 옷_등록(client, 인증)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        await worker.run_once(db_engine)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        await worker.run_once(db_engine)
        assert len(생성기["호출"]) == 1

    async def test_실패한_뒤_다시_요청하면_새_잡이_생긴다(self, client, 인증, db_engine, 생성기):
        # 실패를 재사용하면 재시도가 영영 막힌다 (D6)
        await 전신사진(client, 인증)
        옷 = await 옷_등록(client, 인증)
        await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        생성기["예외"] = RuntimeError("터짐")
        for _ in range(worker.MAX_ATTEMPTS):
            await worker.run_once(db_engine)

        생성기["예외"] = None
        r = await client.post("/fittings", json={"garmentId": 옷}, headers=인증)
        assert r.status_code == 201
        await worker.run_once(db_engine)
        async with AsyncSession(db_engine) as db:
            assert len((await db.scalars(select(Fitting))).all()) == 2
        assert (await client.get(f"/fittings/{r.json()['id']}", headers=인증)).json()["status"] == "완료"

"""D1 · 사진 업로드 · 저장 (plan.md 6절)

전신 사진과 의류 사진을 Supabase Storage 에 올린다.

⚠️ **이 파일이 지키는 것은 「누구의 사진인가」다.** 저장 자체는 SDK 한 줄이고,
   틀리면 비싼 것은 경로다 — 경로를 클라이언트가 정할 수 있으면 남의 전신 사진을
   가리키는 행을 만들 수 있고 서명 URL 이 그대로 발급된다 (CLAUDE.md 6절).

⚠️ **테스트는 실제 Supabase 에 붙지 않는다.** conftest 의 `저장소` 픽스처가
   `images.storage` 를 인메모리로 갈아 끼운다 (CLAUDE.md 2절 — 팀 공용 자원).
"""

import uuid

import pytest

from images.storage import photo_key
from tests.test_photo import 사진, 크기

프로필 = {"height": 175, "weight": 70, "gender": "남성"}
의류 = {"kind": "티셔츠", "sizeName": "M", "shoulder": 48.0, "chestWidth": 51.0, "length": 70.0}


@pytest.fixture
async def 인증(client):
    r = await client.post(
        "/auth/signup", json={"email": "a@b.com", "password": "hunter22", "isOver14": True}
    )
    await client.put("/profile", json=프로필, headers={"Authorization": f"Bearer {r.json()['token']}"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def 파일(raw: bytes, 이름: str = "photo.jpg", 타입: str = "image/jpeg"):
    return {"file": (이름, raw, 타입)}


async def 올리기(client, 인증, raw=None, 의류_id=None):
    주소 = f"/photos/garments/{의류_id}" if 의류_id else "/photos/profile"
    return await client.put(주소, files=파일(raw or 사진(512, 768)), headers=인증)


async def 옷_등록(client, 인증):
    return (await client.post("/garments", json=의류, headers=인증)).json()["id"]


class Test경로는_서버가_만든다:
    """클라이언트가 정하면 남의 사진을 가리킬 수 있다"""

    def test_사용자별로_갈린다(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        assert photo_key(a, "JPEG").startswith(f"{a}/")
        assert photo_key(a, "JPEG") != photo_key(b, "JPEG")

    def test_전신사진과_의류사진이_섞이지_않는다(self):
        나 = uuid.uuid4()
        assert photo_key(나, "JPEG") != photo_key(나, "JPEG", uuid.uuid4())

    def test_의류마다_다르다(self):
        나 = uuid.uuid4()
        assert photo_key(나, "JPEG", uuid.uuid4()) != photo_key(나, "JPEG", uuid.uuid4())

    @pytest.mark.parametrize("fmt,확장자", [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")])
    def test_형식이_확장자로_남는다(self, fmt, 확장자):
        # 다시 받을 때 content-type 을 추측하지 않으려고 키에 박아 둔다
        assert photo_key(uuid.uuid4(), fmt).endswith(f".{확장자}")

    async def test_의류_등록이_경로를_받지_않는다(self, client, 인증):
        # photoPath 를 실어 보내도 무시한다 — 받으면 남의 사진 경로를 넣을 수 있다
        r = await client.post(
            "/garments", json=의류 | {"photoPath": "남의id/profile.jpg"}, headers=인증
        )
        assert r.status_code == 201
        assert r.json()["photoPath"] is None


class Test올리면_저장된다:
    async def test_전신사진_200(self, client, 인증, 저장소):
        r = await 올리기(client, 인증)
        assert r.status_code == 200
        assert r.json()["photoPath"] in 저장소

    async def test_서명_URL_이_같이_온다(self, client, 인증):
        # 비공개 버킷이라 이것 없이는 프론트가 방금 올린 사진도 못 그린다
        assert (await 올리기(client, 인증)).json()["photoUrl"].startswith("https://")

    async def test_프로필_조회에_실려_나온다(self, client, 인증):
        경로 = (await 올리기(client, 인증)).json()["photoPath"]
        r = (await client.get("/profile", headers=인증)).json()
        assert r["photoPath"] == 경로
        assert r["photoUrl"].startswith("https://")

    async def test_의류사진_목록에_실려_나온다(self, client, 인증):
        옷 = await 옷_등록(client, 인증)
        경로 = (await 올리기(client, 인증, 의류_id=옷)).json()["photoPath"]
        목록 = (await client.get("/garments", headers=인증)).json()
        assert 목록[0]["photoPath"] == 경로
        assert 목록[0]["photoUrl"].startswith("https://")

    async def test_사진이_없으면_URL_도_없다(self, client, 인증):
        assert (await client.get("/profile", headers=인증)).json()["photoUrl"] is None
        await 옷_등록(client, 인증)
        assert (await client.get("/garments", headers=인증)).json()[0]["photoUrl"] is None

    async def test_프로필을_다시_저장해도_사진은_남는다(self, client, 인증):
        # PUT /profile 은 전체 교체지만 사진은 그 요청에 실리지 않는다
        경로 = (await 올리기(client, 인증)).json()["photoPath"]
        await client.put("/profile", json=프로필 | {"chest": 92.0}, headers=인증)
        assert (await client.get("/profile", headers=인증)).json()["photoPath"] == 경로


class Test검증은_D2가_한다:
    async def test_작은_사진은_거부된다(self, client, 인증):
        r = await 올리기(client, 인증, raw=사진(400, 600))
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "PHOTO_TOO_SMALL"

    async def test_거부된_사진은_저장되지_않는다(self, client, 인증, 저장소):
        # 검증보다 먼저 올리면 아무도 안 읽는 파일이 계속 쌓인다
        await 올리기(client, 인증, raw=사진(400, 600))
        assert 저장소 == {}

    async def test_사진이_아니면_거부된다(self, client, 인증):
        r = await 올리기(client, 인증, raw=b"this is not an image")
        assert r.json()["error"]["code"] == "PHOTO_UNREADABLE"

    async def test_누운_폰사진은_세워서_저장된다(self, client, 인증, 저장소):
        # D2 의 EXIF 처리가 업로드 경로에도 걸려 있어야 한다
        r = await 올리기(client, 인증, raw=사진(768, 512, orientation=6))
        assert r.status_code == 200
        assert 크기(저장소[r.json()["photoPath"]]) == (512, 768)

    async def test_너무_큰_파일은_읽기_전에_끊는다(self, client, 인증):
        from api.photos import MAX_BYTES

        r = await 올리기(client, 인증, raw=b"\xff" * (MAX_BYTES + 1))
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "PHOTO_TOO_LARGE"


class Test남의_것에_올릴_수_없다:
    async def test_인증이_없으면_401(self, client):
        r = await client.put("/photos/profile", files=파일(사진(512, 768)))
        assert r.status_code == 401

    async def test_남의_의류에는_404(self, client, 인증):
        옷 = await 옷_등록(client, 인증)
        남 = await client.post(
            "/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True}
        )
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        r = await 올리기(client, 헤더, 의류_id=옷)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "GARMENT_NOT_FOUND"

    async def test_없는_의류에도_404(self, client, 인증):
        assert (await 올리기(client, 인증, 의류_id=uuid.uuid4())).status_code == 404

    async def test_프로필이_없으면_404(self, client):
        r = await client.post(
            "/auth/signup", json={"email": "e@f.com", "password": "hunter22", "isOver14": True}
        )
        헤더 = {"Authorization": f"Bearer {r.json()['token']}"}
        assert (await 올리기(client, 헤더)).status_code == 404


class Test다시_올리면_갈아_끼운다:
    async def test_같은_형식이면_경로가_같다(self, client, 인증, 저장소):
        첫째 = (await 올리기(client, 인증)).json()["photoPath"]
        둘째 = (await 올리기(client, 인증, raw=사진(600, 900))).json()["photoPath"]
        assert 둘째 == 첫째
        assert len(저장소) == 1
        assert 크기(저장소[둘째]) == (600, 900)      # 옛 사진이 아니라 새 사진이 남는다

    async def test_형식이_바뀌면_옛_파일을_지운다(self, client, 인증, 저장소):
        # 확장자가 키에 있어 경로가 갈린다. 안 지우면 아무도 안 읽는 파일이 쌓인다
        첫째 = (await 올리기(client, 인증)).json()["photoPath"]
        둘째 = (await 올리기(client, 인증, raw=사진(512, 768, "PNG"))).json()["photoPath"]
        assert 둘째 != 첫째
        assert 첫째 not in 저장소
        assert list(저장소) == [둘째]

    async def test_의류_사진은_서로_안_덮는다(self, client, 인증, 저장소):
        A, B = await 옷_등록(client, 인증), await 옷_등록(client, 인증)
        await 올리기(client, 인증, 의류_id=A)
        await 올리기(client, 인증, 의류_id=B)
        assert len(저장소) == 2


class Test계정을_지우면_사진도_지운다:
    """전신 사진이다. 계정을 지웠는데 남아 있으면 그게 사고다"""

    async def test_전신사진과_의류사진이_같이_사라진다(self, client, 인증, 저장소):
        옷 = await 옷_등록(client, 인증)
        await 올리기(client, 인증)
        await 올리기(client, 인증, 의류_id=옷)
        assert len(저장소) == 2

        assert (await client.delete("/auth/me", headers=인증)).status_code == 204
        assert 저장소 == {}

    async def test_남의_사진은_안_지운다(self, client, 인증, 저장소):
        await 올리기(client, 인증)
        남 = await client.post(
            "/auth/signup", json={"email": "c@d.com", "password": "hunter22", "isOver14": True}
        )
        헤더 = {"Authorization": f"Bearer {남.json()['token']}"}
        await client.put("/profile", json=프로필, headers=헤더)
        남의것 = (await 올리기(client, 헤더)).json()["photoPath"]

        await client.delete("/auth/me", headers=인증)
        assert list(저장소) == [남의것]

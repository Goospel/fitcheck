"""테스트용 인메모리 DB.

⚠️ **팀 공용 DB 에 절대 붙지 않는다** (CLAUDE.md 2절). SQLite 를 메모리에 띄워
매 테스트마다 새로 만든다 — 가짜 세션을 손으로 짜는 것보다 짧고, 유니크 제약처럼
「진짜 DB 만 잡는 것」까지 잡힌다.

⚠️ **외부 API 도 안 부른다** — 아래 `비전검증_끄기` 참고.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.config import settings
from db.models import Base
from db.session import get_session
from main import app


@pytest.fixture(autouse=True)
def 비전검증_끄기(monkeypatch):
    """D2 비전 검증을 전 테스트에서 끈다. **실측으로 배운 것이다.**

    이 검증은 `PUT /photos/profile` 에 붙어 있어서, 끄지 않으면 사진을 올리는
    테스트마다 OpenAI 를 때린다. 실제로 붙이자마자 **12초짜리 스위트가 111초**가
    되고 31건이 깨졌다 — 테스트 픽스처는 합성 이미지라 「사람 없음」으로 정직하게
    거부당한 것이다. 느린 것보다 **돈이 나가는 쪽**이 더 나쁘다.

    판정 로직은 `tests/test_vision.py` 가 순수 함수(`verdict`)로 따로 시험한다.
    """
    monkeypatch.setattr(settings, "vision_check", False)


@pytest.fixture
async def db_engine():
    # StaticPool — 커넥션마다 새 메모리 DB 가 생기는 걸 막는다
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # ⚠️ SQLite 는 외래키를 **기본적으로 안 지킨다.** 켜지 않으면 ON DELETE CASCADE 가
    # 조용히 아무 일도 안 해서 「계정을 지우면 딸린 것도 지워진다」는 확인이 거짓이 된다
    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch):
    """테스트에서만 bcrypt 비용을 낮춘다.

    기본 라운드(12)는 **일부러 느리게** 설계된 값이라 그대로 두면 전체 스위트가
    분 단위로 늘어난다. 운영 코드는 건드리지 않고 여기서만 4로 내린다.
    """
    import bcrypt

    원본 = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda rounds=4, prefix=b"2b": 원본(4, prefix))


@pytest.fixture(autouse=True)
def 저장소(monkeypatch):
    """가짜 Supabase Storage.

    ⚠️ **autouse 다.** 픽스처를 요청하는 걸 잊은 테스트가 실제 저장소에 붙는 일이
    없어야 한다 — 팀 공용 자원이다 (CLAUDE.md 2절).
    """
    from images import storage

    파일: dict[str, bytes] = {}

    async def upload(key, data, fmt):
        파일[key] = data

    async def download(key):
        if key not in 파일:
            raise RuntimeError(f"없는 파일: {key}")
        return 파일[key]

    async def signed_urls(keys):
        # 없는 키는 빠진다 — 진짜 Storage 도 그 항목에 error 를 실어 준다
        return {k: f"https://signed.test/{k}?token=fake" for k in dict.fromkeys(keys) if k in 파일}

    async def remove(keys):
        for k in keys:
            파일.pop(k, None)

    async def remove_user_photos(user_id):
        for k in [k for k in 파일 if k.startswith(f"{user_id}/")]:
            del 파일[k]

    for 이름, 가짜 in (("upload", upload), ("signed_urls", signed_urls), ("download", download),
                     ("remove", remove), ("remove_user_photos", remove_user_photos)):
        monkeypatch.setattr(storage, 이름, 가짜)
    return 파일

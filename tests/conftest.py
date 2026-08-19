"""테스트용 인메모리 DB.

⚠️ **팀 공용 DB 에 절대 붙지 않는다** (CLAUDE.md 2절). SQLite 를 메모리에 띄워
매 테스트마다 새로 만든다 — 가짜 세션을 손으로 짜는 것보다 짧고, 유니크 제약처럼
「진짜 DB 만 잡는 것」까지 잡힌다.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from db.models import Base
from db.session import get_session
from main import app


@pytest.fixture
async def db_engine():
    # StaticPool — 커넥션마다 새 메모리 DB 가 생기는 걸 막는다
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
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

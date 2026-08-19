"""B0(코드 몫) · async 엔진 · 세션

⚠️ **엔진을 임포트 시점에 만들지 않는다.** `DATABASE_URL` 이 없어도 앱은 떠야
한다 (core/config.py 와 같은 약속) — 라우터를 임포트했다는 이유만으로 앱이
죽으면 fit/ 같은 순수 로직 작업까지 같이 멈춘다. 처음 쓸 때 만들고, 그때도
설정이 없으면 500 이 아니라 503 으로 떨어진다.
"""

import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from core.errors import AppError
from db.models import Base


@lru_cache(maxsize=1)
def engine() -> AsyncEngine:
    if not settings.database_url:
        raise AppError("DB_NOT_CONFIGURED", "서버 설정이 아직 준비되지 않았습니다", 503)
    # Supabase 는 유휴 커넥션을 끊는다. pre_ping 이 없으면 간헐적으로 끊긴 커넥션을 집는다
    return create_async_engine(settings.database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False — commit 뒤에도 객체를 그대로 읽을 수 있게 (async 에서 재조회는 await 다)
    return async_sessionmaker(engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 의존성.  `async def 핸들러(db: AsyncSession = Depends(get_session))`"""
    async with _sessionmaker()() as session:
        yield session


async def create_tables() -> None:
    """초기 생성 1회. 마이그레이션 도구를 쓰지 않는다 (plan.md 8절).

    ⚠️ 이후 스키마 변경은 create_all 이 안 잡는다. 손으로 ALTER 를 돌리고 팀에 알린다.
    """
    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":   # uv run python -m db.session
    asyncio.run(create_tables())

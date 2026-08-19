"""D4 · 이미지 생성 워커 — Redis 없이 `image_job` 테이블 자체가 큐다.

`FOR UPDATE SKIP LOCKED` 로 집어간다 (CLAUDE.md 2절). 워커가 여럿 떠도
같은 잡을 두 번 집지 않는다 — 커밋되기 전까지 그 행은 잠겨 있다.
"""

import asyncio
import logging
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import Fitting, Garment, ImageJob, Profile
from db.session import engine
from fit.report import FitReport
from images import generate, prompt, storage

logger = logging.getLogger(__name__)

# 잡 하나가 일시적 API 오류(레이트리밋 등)로 죽었다고 바로 "실패"로 굳히면
# 사용자가 손으로 다시 만들어야 한다 — 몇 번은 다시 시도한다
MAX_ATTEMPTS = 3

# 폴링 주기(초). docs/contracts.md 가 "D4 에서 확정한다"고 적어 둔 백엔드 쪽 값.
# 단일 워커·해커톤 규모에서 빈 폴의 DB 왕복 비용보다 반응 속도가 더 중요하다
POLL_INTERVAL = 2.0


@lru_cache(maxsize=1)
def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    """db/session.py 와 같은 패턴이지만 요청-응답 밖(백그라운드 루프)이라
    FastAPI 의 `Depends(get_session)` 을 못 쓴다 — 여기서 따로 세션을 연다."""
    return async_sessionmaker(engine(), expire_on_commit=False)


async def claim_next(db: AsyncSession) -> ImageJob | None:
    """대기 중인 잡 하나를 집어 "생성중"으로 표시하고 커밋한다.

    ⚠️ `SKIP LOCKED` 가 없으면 워커 두 개가 같은 「대기」 행을 동시에 읽어
       똑같이 유료 API 를 두 번 부른다 — 여기가 Redis 없이 큐가 성립하는 지점이다.
    """
    job = (
        await db.execute(
            select(ImageJob)
            .where(ImageJob.status == "대기")
            .order_by(ImageJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "생성중"
    job.attempts += 1
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    return job


async def _fail(db: AsyncSession, job_id, error: str) -> None:
    """재조회해서 다시 쓴다 — 호출자 쪽에서 이미 rollback 이 지나가 객체가 만료돼 있을 수 있다."""
    job = await db.get(ImageJob, job_id)
    job.error = error[:500]
    if job.attempts >= MAX_ATTEMPTS:
        job.status = "실패"
        job.finished_at = datetime.now(timezone.utc)
    else:
        job.status = "대기"          # 다음 폴에서 다시 집힌다
    await db.commit()


async def process(db: AsyncSession, job: ImageJob) -> None:
    """집어 온 잡 하나를 끝까지: 다운로드 → 프롬프트 → 생성 → 업로드 → 상태 갱신.

    ⚠️ 실패를 여기서 삼킨다. 워커 루프가 예외로 죽으면 뒤에 쌓인 다른 사람의
       잡까지 전부 멈춘다 — 한 건의 실패가 큐 전체를 막으면 안 된다.
    """
    fitting = await db.get(Fitting, job.fitting_id)
    garment = await db.get(Garment, fitting.garment_id)
    profile = await db.get(Profile, fitting.user_id)

    try:
        if profile is None or not profile.photo_path or not garment.photo_path:
            # 큐에 들어왔다는 것 자체가 두 사진이 있었다는 뜻이라 정상 경로로는 안 온다.
            # 그 사이 사진이 새로 올라와 경로가 바뀌었을 때만 방어적으로 걸린다
            raise RuntimeError("사진 경로를 찾을 수 없습니다")

        person_bytes = await storage.download(profile.photo_path)
        garment_bytes = await storage.download(garment.photo_path)
        text = prompt.build_prompt(FitReport.model_validate(fitting.report))

        image = await generate.generate_tryon(
            text,
            (person_bytes, storage.mime_of(profile.photo_path)),
            (garment_bytes, storage.mime_of(garment.photo_path)),
        )

        key = storage.result_key(fitting.user_id, fitting.id)
        await storage.upload(key, image, "PNG")

        fitting.image_path = key
        job.status = "완료"
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as e:
        await db.rollback()
        await _fail(db, job.id, str(e))


async def reset_orphaned_jobs() -> None:
    """서버가 「생성중」인 채로 죽었다 살아나면 그 잡들은 영원히 「생성중」으로 남는다.

    시작할 때 한 번, 이 프로세스가 아직 아무것도 집기 전에 부른다 — 그 시점의
    「생성중」은 전부 지난 프로세스가 남기고 간 것이다.
    """
    async with _sessionmaker()() as db:
        rows = await db.scalars(select(ImageJob).where(ImageJob.status == "생성중"))
        for job in rows:
            job.status = "대기"
        await db.commit()


async def _loop() -> None:
    while True:
        try:
            async with _sessionmaker()() as db:
                job = await claim_next(db)
            if job is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            async with _sessionmaker()() as db:
                await process(db, job)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("이미지 잡 루프에서 잡히지 않은 예외")
            await asyncio.sleep(POLL_INTERVAL)


_task: asyncio.Task | None = None


def start_workers() -> None:
    global _task
    if _task is None:
        _task = asyncio.create_task(_loop())


async def stop_workers() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None

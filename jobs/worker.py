"""D4 · 비동기 잡 큐 + D5 · 타임아웃·실패 처리

생성이 2분 걸린다 (D0 실측 115초). 요청을 붙잡고 기다릴 수 없으니 `image_job` 에
넣고 워커가 가져간다 — **창을 닫거나 재접속해도 결과가 유실되지 않는다** (PRD 7.5).

⚠️ **큐가 곧 테이블이다.** Redis·Celery 를 붙이지 않는다 (CLAUDE.md 2절). 붙일 것이
   하나 늘면 배포·설정·장애 지점이 하나씩 는다. `FOR UPDATE SKIP LOCKED` 면 워커
   여럿이 같은 잡을 집는 일이 없다.

⚠️ **여기서 지켜야 할 것은 「빈손으로 돌아가지 않는다」다** (F-09). 생성이 터져도 ·
   시간이 넘어도 · 재배포로 죽어도 **핏 리포트는 그대로 남는다.** 잡이 실패하면
   `fitting.image_path` 만 비어 있을 뿐이다.
"""

import asyncio
import contextlib
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from db.models import Fitting, Garment, ImageJob, Profile, _now
from fit.report import FitReport
from images import generate, storage
from images.prompt import build_prompt

log = logging.getLogger("fitcheck.jobs")

# 잡 하나의 상한. **PRD 확정 상수다** (CLAUDE.md 1절 — 이미지 생성 타임아웃 10분).
# 실측은 115초라 한참 여유가 있지만, 상한은 스펙이 정한 값을 쓴다
TIMEOUT_SECONDS = 600

# 몇 번까지 해 보는가. 1 이면 일시적 오류 한 번에 사용자가 빈손이 되고,
# 크게 잡으면 결정적 실패에 유료 호출을 그만큼 태운다
MAX_ATTEMPTS = 2

# 동시에 몇 건. plan.md D4 가 「최소 5건」이라 5 다
WORKERS = 5

# 큐를 얼마나 자주 보는가. 생성이 2분짜리라 이 정도면 체감이 없고, 더 짧으면 DB 만 때린다
POLL_SECONDS = 3

_tasks: list[asyncio.Task] = []


async def _claim(db: AsyncSession) -> uuid.UUID | None:
    """대기 중인 잡 하나를 집어 「생성중」으로 바꾸고 **그 id** 를 돌려준다. 없으면 None.

    ⚠️ ORM 객체를 돌려주지 않는다 — 세션 밖으로 나간 객체는 속성 하나 읽는 순간
       터진다(`expire_on_commit`). id 는 그냥 값이라 어디로든 들고 갈 수 있다.

    ⚠️ **같은 잡을 두 번 집는 것을 막는 것은 `SKIP LOCKED` 가 아니라 `WHERE` 다.**
       행을 잠근 뒤 Postgres 가 조건을 다시 보므로(EvalPlanQual), 먼저 집은 쪽이
       「생성중」으로 바꿔 커밋하면 뒤에 온 쪽은 그 행을 그냥 놓친다. 실제 Postgres 로
       확인했다 — `SKIP LOCKED` 를 떼도 다섯이 동시에 집어 **중복 0건**이었다.

    ⚠️ **`SKIP LOCKED` 가 하는 일은 「기다리지 않기」다.** 잠긴 행을 만나면 건너뛰고
       다음 것을 본다. 없으면 잠금이 풀릴 때까지 선다 — 실측: 다른 세션이 행을 2초
       붙잡고 있을 때 **0.17초 vs 2.05초**. 워커 다섯을 띄우는 의미가 여기서 난다.

    ⚠️ SQLite 는 행 잠금이 없어 SQLAlchemy 가 이 구절을 **조용히 빼고** 컴파일한다.
       테스트는 상태 전이만 볼 수 있고, 잠금은 실제 Postgres 로만 잰다.
    """
    job = await db.scalar(
        select(ImageJob)
        .where(ImageJob.status == "대기")
        .order_by(ImageJob.created_at)      # 오래 기다린 것부터
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = "생성중"
    job.started_at = _now()
    job.attempts += 1                        # 집어간 순간 센다 — 죽어도 무한 재시도가 안 되게
    잡id = job.id
    await db.commit()
    return 잡id


async def _재료(fitting: Fitting, db: AsyncSession) -> tuple[bytes, bytes, str]:
    """모델에 넘길 사진 두 장과 지시문.

    사진은 **생성 시점에** 읽는다. 리포트는 요청 시점 스냅샷이지만(D6) 사진은
    최신 것이 맞다 — 사진을 바꾼 뒤 나온 결과가 옛 사진이면 그게 더 이상하다.
    """
    profile = await db.get(Profile, fitting.user_id)
    garment = await db.get(Garment, fitting.garment_id)
    # 빈 경로면 어차피 `download` 에서 터진다. 그래도 여기서 끊는 이유는 **잡의
    # error 컬럼에 남을 문구** 때문이다 — AttributeError 보다 이쪽이 원인을 말해 준다
    if profile is None or not profile.photo_path or garment is None or not garment.photo_path:
        raise RuntimeError("생성에 필요한 사진이 없습니다")
    return (
        await storage.download(profile.photo_path),
        await storage.download(garment.photo_path),
        build_prompt(FitReport.model_validate(fitting.report)),
    )


async def _process(job_id: uuid.UUID, db: AsyncSession) -> None:
    """집어 온 잡 하나를 끝까지. **예외를 밖으로 내보내지 않는다** — 워커 루프가
    이걸로 죽으면 큐가 통째로 선다."""
    job = await db.get(ImageJob, job_id)
    fitting = await db.get(Fitting, job.fitting_id)
    try:
        person, garment, prompt = await _재료(fitting, db)
        async with asyncio.timeout(TIMEOUT_SECONDS):
            그림 = await generate.generate_image(person, garment, prompt)

        key = storage.result_key(fitting.user_id, fitting.id)
        await storage.upload(key, 그림, "PNG")
        fitting.image_path = key
        job.status, job.error = "완료", None
    except asyncio.CancelledError:
        raise                                # 종료 신호는 삼키지 않는다
    except Exception as e:
        # ⚠️ 문구를 사용자에게 그대로 보여주지 않는다 — 모델 응답에 키가 섞일 수 있다.
        #    응답 스키마에 `error` 가 없는 것이 그 처리다 (api/fittings.py)
        사유 = f"{type(e).__name__}" if isinstance(e, TimeoutError) else str(e)
        job.error = 사유[:500]
        # 일시적 오류일 수 있다. 시도가 남았으면 큐로 되돌린다
        job.status = "대기" if job.attempts < MAX_ATTEMPTS else "실패"
        log.warning("이미지 생성 실패 (job=%s, attempts=%s): %s", job_id, job.attempts, 사유)

    if job.status in ("완료", "실패"):
        job.finished_at = _now()
    await db.commit()


async def run_once(engine: AsyncEngine) -> bool:
    """잡 하나를 집어 처리한다. 집을 게 없으면 False.

    루프와 분리해 둔 이유 — **테스트가 한 건씩 결정적으로 돌릴 수 있다.**
    """
    async with AsyncSession(engine) as db:
        잡id = await _claim(db)
    if 잡id is None:
        return False
    async with AsyncSession(engine) as db:
        await _process(잡id, db)
    return True


async def sweep_zombies(engine: AsyncEngine) -> None:
    """D5 · 시작할 때 「생성중」으로 남아 있는 잡을 정리한다.

    서버가 죽으면 집어간 잡이 **영원히 생성중**으로 남는다 — 사용자는 끝나지 않는
    스피너를 본다. 재배포마다 여기서 턴다.

    ⚠️ **plan.md 는 「전부 실패로 민다」였는데 「시도가 남았으면 큐로 되돌린다」로
       바꿨다.** 재배포는 사용자 잘못이 아니라 우리 사정이고, 큐로 되돌리면 그냥
       이어서 끝난다. `attempts` 는 집어갈 때 이미 셌으므로 무한 반복은 안 된다.
    """
    async with AsyncSession(engine) as db:
        for 다음, 조건 in (("대기", ImageJob.attempts < MAX_ATTEMPTS),
                          ("실패", ImageJob.attempts >= MAX_ATTEMPTS)):
            await db.execute(
                update(ImageJob)
                .where(ImageJob.status == "생성중", 조건)
                .values(status=다음, error="서버가 다시 시작되어 중단되었습니다",
                        finished_at=_now() if 다음 == "실패" else None)
            )
        await db.commit()


async def _loop(engine: AsyncEngine, 번호: int) -> None:
    """⚠️ **무슨 일이 있어도 루프를 유지한다.** 워커 하나가 조용히 죽으면 처리량이
    줄고, 다섯이 다 죽으면 큐가 영영 선다."""
    while True:
        try:
            if not await run_once(engine):
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("워커 %s 가 예상 못한 오류를 만났다", 번호)
            await asyncio.sleep(POLL_SECONDS)


async def start() -> None:
    """앱 startup 에서 부른다. **설정이 없으면 조용히 안 뜬다** — `DATABASE_URL` 이
    없어도 앱은 떠야 한다는 약속(db/session.py)을 워커가 깨면 안 된다."""
    from db.session import engine

    try:
        eng = engine()
    except Exception as e:
        log.warning("워커를 띄우지 않는다 — %s", e)
        return

    await sweep_zombies(eng)
    _tasks.extend(asyncio.create_task(_loop(eng, i)) for i in range(WORKERS))
    log.info("워커 %d개 시작", WORKERS)


async def stop() -> None:
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await t
    _tasks.clear()

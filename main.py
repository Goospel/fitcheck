from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.errors import register_error_handlers
from jobs import worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB 가 없어도 앱은 떠야 한다 (core/config.py 와 같은 약속) — 워커도 그 값을 따른다
    if settings.database_url:
        await worker.reset_orphaned_jobs()
        worker.start_workers()
    yield
    await worker.stop_workers()


app = FastAPI(title="FitCheck API", docs_url="/docs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

# 라우터 등록 — 자기 줄만 추가하고 남의 줄은 건드리지 않는다 (CLAUDE.md 3절)
from api import fittings, garments            # BE-1
from api import auth, profile                 # BE-2
from api import photos                     # BE-3
# from api import history, results

app.include_router(garments.router)
app.include_router(fittings.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(photos.router)


@app.get("/health")
def health():
    return {"status": "ok"}

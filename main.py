from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.errors import register_error_handlers
from jobs import worker                       # BE-3


@asynccontextmanager
async def lifespan(_: FastAPI):
    """D4 · 이미지 생성 워커를 여기서 띄우고 내린다 (BE-3).

    ⚠️ **설정이 없으면 워커만 조용히 안 뜬다.** `DATABASE_URL` 이 없어도 앱은 떠야
       한다는 약속(db/session.py)을 워커가 깨면 안 된다.
    """
    await worker.start()
    yield
    await worker.stop()


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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.errors import register_error_handlers

app = FastAPI(title="FitCheck API", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

# 라우터 등록 — 자기 줄만 추가하고 남의 줄은 건드리지 않는다 (CLAUDE.md 3절)
# from api import garments, fittings          # BE-1
# from api import auth, profile               # BE-2
# from api import history, results            # BE-3
# app.include_router(garments.router)


@app.get("/health")
def health():
    return {"status": "ok"}

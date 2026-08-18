from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class AppError(Exception):
    """서비스 에러는 전부 이걸 올린다. 각자 다른 모양으로 뱉지 않는다.

        raise AppError("GARMENT_NOT_FOUND", "의류를 찾을 수 없습니다", 404)
    """

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def error_body(code: str, message: str) -> dict:
    """확정된 에러 응답 모양. 프론트가 이 키를 그대로 읽는다."""
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())[1:]) or "요청"
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", f"{field} 값이 올바르지 않습니다"),
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        # 라우팅 404 등 프레임워크가 직접 올리는 것들도 같은 모양으로 맞춘다
        return JSONResponse(status_code=exc.status_code, content=error_body("HTTP_ERROR", str(exc.detail)))

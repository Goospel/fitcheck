"""core/ 골격 자체가 깨지지 않았는지 보는 최소 검사.

셋이 전부 여기 의존하므로 이게 깨지면 세 명의 API가 동시에 어긋난다.
"""

from fastapi.testclient import TestClient

from core.errors import AppError
from core.schema import Schema
from main import app

client = TestClient(app, raise_server_exceptions=False)


def test_응답은_camelCase로_나간다():
    class FitReport(Schema):
        chest_ease: int
        fit_grade: str

    assert FitReport(chest_ease=18, fit_grade="세미오버핏").model_dump(by_alias=True) == {
        "chestEase": 18,
        "fitGrade": "세미오버핏",
    }


def test_AppError는_확정된_모양으로_나간다():
    @app.get("/_test/boom")
    def boom():
        raise AppError("GARMENT_NOT_FOUND", "의류를 찾을 수 없습니다", 404)

    res = client.get("/_test/boom")
    assert res.status_code == 404
    assert res.json() == {
        "error": {"code": "GARMENT_NOT_FOUND", "message": "의류를 찾을 수 없습니다"}
    }


def test_검증실패도_같은_모양으로_나간다():
    @app.get("/_test/param")
    def param(size: int):
        return {"size": size}

    res = client.get("/_test/param?size=사이즈아님")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_없는_경로도_같은_모양으로_나간다():
    res = client.get("/_test/없는경로")
    assert res.status_code == 404
    assert "error" in res.json()

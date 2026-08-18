from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    """모든 요청·응답 모델의 베이스. 요청·응답 모델은 전부 이걸 상속한다.

    파이썬 내부는 snake_case로 쓰되 밖으로 나가는 JSON 키만 camelCase가 된다
    (CLAUDE.md 5절). 손으로 맞추지 않는다.

        class FitReport(Schema):
            chest_ease: int
            fit_grade: str

        # → {"chestEase": 18, "fitGrade": "세미오버핏"}
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,   # 파이썬 안에서는 snake_case로도 생성 가능
        from_attributes=True,    # SQLAlchemy 객체를 그대로 넘길 수 있게
    )

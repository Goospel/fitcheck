from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 로딩. 값이 없어도 앱이 뜨게 전부 기본값을 둔다.

    Supabase가 아직 없어도 fit/ 같은 순수 로직 작업은 시작할 수 있어야 한다.
    새 환경변수를 추가하면 .env.example도 같이 갱신한다 (CLAUDE.md 3절).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    # ⚠️ 32바이트 이상. 미만이면 PyJWT 가 경고하고 서명이 약해진다
    jwt_secret: str = "dev-only-not-for-production-change-this-value"
    jwt_expire_hours: int = 168

    # ── 이미지 생성 ──
    # OpenAI 로 간다. 멋사 팀 조직에 크레딧이 있어 카드 없이 쓸 수 있고,
    # Replicate 는 품질이 안 나올 때를 위한 **예비 경로**로 남겨 둔다 (D0 판단)
    openai_api_key: str = ""
    # D0 에서 모델을 갈아 끼우며 비교한다. 코드가 아니라 환경변수로 바꾼다
    image_model: str = "gpt-image-2"
    replicate_api_token: str = ""

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

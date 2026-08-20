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
    # OpenAI 로 확정했다 (D0). 멋사 팀 조직에 크레딧이 있어 카드가 필요 없다
    openai_api_key: str = ""
    # 모델은 코드가 아니라 환경변수로 바꾼다 — 갈아 끼울 때 배포만 하면 된다
    image_model: str = "gpt-image-2"

    # ── CORS ──
    # 정해진 도메인은 여기 쉼표로 나열한다. 프론트 배포처가 확정되면 이쪽이 정답이다
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # ⚠️ **프리뷰 배포는 호스트가 매번 바뀐다.** Vercel·Netlify 는 푸시마다
    #    `fitcheck-a1b2c3-team.vercel.app` 같은 새 주소를 만든다. 고정 목록만 두면
    #    프론트가 푸시할 때마다 백엔드를 고쳐야 해서, 패턴으로도 받는다.
    #
    # ⚠️ **`.*` 로 시작하는 패턴을 쓰지 않는다.** Starlette 는 `fullmatch` 라
    #    접미사 공격(`vercel.app.evil.com`)은 원래 막히지만, 앞에 `.*` 를 붙이는
    #    순간 뚫린다. 호스트 라벨을 명시해 **직접 등록 가능한 유사 도메인**
    #    (`evil-vercel.app`)까지 막는다. 회귀는 tests/test_cors.py 가 잡는다.
    #
    # 배포 도메인이 정해지면 `cors_origins` 에 넣고 이 값을 좁히거나 비우면 된다.
    cors_origin_regex: str = (
        r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?"
        r"|https://[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
        r"\.(?:vercel\.app|netlify\.app|pages\.dev|github\.io)"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

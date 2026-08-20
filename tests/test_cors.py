"""CORS — 배포처가 안 정해져도 막히지 않게, 그렇다고 아무나 통과시키지도 않게

⚠️ **프리뷰 배포는 URL 이 매번 바뀐다.** Vercel·Netlify 는 푸시마다
`fitcheck-a1b2c3-team.vercel.app` 처럼 새 호스트를 만든다. 고정 목록만 두면
프론트가 푸시할 때마다 백엔드를 고쳐야 한다.

⚠️ **그래서 정규식을 쓰는데, 여기가 실수하면 아무 사이트나 통과한다.**
Starlette 는 `fullmatch` 로 검사하므로(1.0.1 실측) 접미사만 맞는
`https://vercel.app.evil.com` 은 애초에 안 걸린다. 하지만 **직접 등록 가능한
비슷한 도메인**(`evil-vercel.app` · `myvercel.app`)은 패턴을 느슨하게 쓰면 통과한다.
아래 「막아야 하는 것」이 그걸 지킨다.

브라우저가 아닌 클라이언트(네이티브 앱·서버)는 CORS 자체가 적용되지 않는다.
여기서 막는 것은 **남의 웹페이지가 사용자 브라우저를 빌려 우리 API 를 부르는 것**뿐이다.
"""

import pytest


async def preflight(client, origin: str):
    """브라우저가 실제 요청 전에 보내는 그 요청"""
    return await client.options(
        "/auth/check",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def 허용됐나(응답, origin: str) -> bool:
    # 허용이면 서버가 그 출처를 그대로 되울려 준다. 거부면 헤더 자체가 없다
    return 응답.headers.get("access-control-allow-origin") == origin


class Test로컬_개발은_포트를_안_가린다:
    """vite 는 5173 이 물려 있으면 5174 로 옮겨 뜬다. 그때마다 백엔드를 고칠 순 없다"""

    @pytest.mark.parametrize("origin", [
        "http://localhost:3000",     # next dev
        "http://localhost:5173",     # vite dev
        "http://localhost:5174",     # vite 가 포트를 옮겼을 때
        "http://localhost:4173",     # vite preview
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ])
    async def test_통과한다(self, client, origin):
        assert 허용됐나(await preflight(client, origin), origin)


class Test프리뷰_배포는_호스트가_매번_바뀐다:
    @pytest.mark.parametrize("origin", [
        "https://fitcheck.vercel.app",
        "https://fitcheck-git-main-teamname.vercel.app",   # 브랜치 프리뷰
        "https://fitcheck-a1b2c3d4.vercel.app",            # 커밋 프리뷰
        "https://fitcheck.netlify.app",
        "https://deploy-preview-7--fitcheck.netlify.app",
        "https://fitcheck.pages.dev",                      # Cloudflare Pages
        "https://goospel.github.io",                       # GitHub Pages
    ])
    async def test_통과한다(self, client, origin):
        assert 허용됐나(await preflight(client, origin), origin)


class Test막아야_하는_것:
    """⚠️ 여기가 이 파일의 존재 이유다. 통과시키면 안 되는 것들"""

    @pytest.mark.parametrize("origin", [
        "https://evil.com",
        "http://evil.com",
        # 접미사만 맞는 것 — fullmatch 라 원래 안 걸리지만, 누가 패턴 앞에 .* 를
        # 붙이는 순간 뚫린다. 그 회귀를 여기서 잡는다
        "https://vercel.app.evil.com",
        "https://fitcheck.vercel.app.evil.com",
        "https://netlify.app.evil.com",
        # **직접 등록 가능한 비슷한 도메인** — 느슨한 패턴이면 진짜로 통과한다
        "https://evil-vercel.app",
        "https://myvercel.app",
        "https://notnetlify.app",
        "https://pages.dev.evil.com",
        # 서브도메인 없는 본체
        "https://vercel.app",
        "https://netlify.app",
        # localhost 를 흉내낸 것
        "http://localhost.evil.com",
        "http://evil.com:3000",
        # 스킴만 다른 것도 다른 출처다
        "ftp://localhost:3000",
    ])
    async def test_막힌다(self, client, origin):
        assert not 허용됐나(await preflight(client, origin), origin)


class Test기존_동작은_그대로다:
    async def test_고정_목록도_여전히_통과한다(self, client):
        # 환경변수 CORS_ORIGINS 로 도메인이 정해지면 그 경로로 들어온다
        from core.config import settings

        for origin in settings.cors_origin_list:
            assert 허용됐나(await preflight(client, origin), origin)

    async def test_Origin_없는_요청은_CORS_와_무관하다(self, client):
        # 서버·네이티브 앱·curl — 브라우저가 아니면 Origin 을 안 보낸다
        r = await client.post("/auth/check", json={"email": "a@b.com"})
        assert r.status_code == 200

    async def test_허용된_출처는_메서드가_다_열려_있다(self, client):
        r = await preflight(client, "https://fitcheck.vercel.app")
        허용 = r.headers.get("access-control-allow-methods", "")
        for m in ("GET", "POST", "PUT", "DELETE"):
            assert m in 허용, 허용


class Test패턴_자체를_직접_본다:
    """미들웨어를 안 거치고 정규식만 — 어디가 틀렸는지 바로 보인다"""

    def test_비어_있지_않다(self):
        from core.config import settings

        assert settings.cors_origin_regex, "정규식이 비면 프리뷰 배포가 전부 막힌다"

    def test_fullmatch_로_쓰인다(self):
        # Starlette 가 fullmatch 를 쓴다는 전제에 기대고 있다. 버전이 올라가며
        # match 로 바뀌면 접미사 공격이 열리므로 여기서 잡는다
        import inspect

        from starlette.middleware import cors

        assert "fullmatch" in inspect.getsource(cors.CORSMiddleware.is_allowed_origin)

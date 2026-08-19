"""B1 · DB 스키마 — 계약 1

DB 없이 검증한다. **PostgreSQL 방언으로 DDL을 컴파일**하면 타입·관계·제약이
깨진 게 전부 여기서 터진다. 실 DB에 쓰지 않는다 (CLAUDE.md 2절 — 팀 공용 DB).
"""

import pytest
from sqlalchemy import JSON as sa_JSON
from sqlalchemy import String as sa_String
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from db.models import Base, Fitting, Garment, ImageJob, Profile, User

모델들 = [User, Profile, Garment, Fitting, ImageJob]


def ddl(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


class Test다섯_테이블이_다_있다:
    def test_계약_1이_요구한_테이블(self):
        assert set(Base.metadata.tables) == {
            "app_user", "profile", "garment", "fitting", "image_job",
        }

    @pytest.mark.parametrize("model", 모델들, ids=lambda m: m.__name__)
    def test_DDL이_컴파일된다(self, model):
        # 타입·관계·제약이 깨져 있으면 여기서 터진다
        assert ddl(model).startswith("\nCREATE TABLE")


class Test예약어_함정:
    """`user` 는 PostgreSQL 예약어다 — `select * from user` 가 에러가 아니라
    현재 접속 사용자를 돌려준다. 조용히 틀리므로 테이블명 자체를 피한다."""

    def test_테이블명이_app_user다(self):
        assert User.__tablename__ == "app_user"
        assert "user" not in Base.metadata.tables


class Test비밀번호는_해시만_남는다:
    """CLAUDE.md 6절 — 평문 저장 금지"""

    def test_해시_컬럼만_있다(self):
        컬럼 = set(User.__table__.columns.keys())
        assert "password_hash" in 컬럼
        assert "password" not in 컬럼

    def test_이메일은_유일하다(self):
        assert User.__table__.c.email.unique is True


class Test프로필_치수는_비어_있을_수_있다:
    """**NULL = 추정.** 실측값만 저장하고 출처는 NULL 여부로 판별한다.

    plan.md 는 「출처 플래그를 같이 저장」이라 썼지만, 값이 있으면 실측·없으면
    추정이므로 플래그 4개는 컬럼이 아니라 파생이다. A4 가 나중에 붙어도 기존
    행이 자동으로 추정값을 얻는다 (플래그를 저장하면 재저장 전까지 비어 있다).
    """

    @pytest.mark.parametrize("치수", ["shoulder", "chest", "waist", "arm"])
    def test_실측_4개가_nullable이다(self, 치수):
        assert Profile.__table__.c[치수].nullable is True

    @pytest.mark.parametrize("플래그", ["shoulder_source", "chest_source", "waist_source"])
    def test_출처_플래그_컬럼은_두지_않는다(self, 플래그):
        assert 플래그 not in Profile.__table__.columns

    def test_선호_핏도_비어_있을_수_있다(self):
        # 미설정이면 계약 2 의 showPreferenceCta 가 켜진다
        assert Profile.__table__.c.preferred_grade.nullable is True

    def test_계정을_지우면_프로필도_지워진다(self):
        # C5 계정 삭제 — 프로필·사진·피팅 전부 즉시 삭제
        (fk,) = Profile.__table__.c.user_id.foreign_keys
        assert fk.ondelete == "CASCADE"


class Test확정_상수가_DB에도_박혀_있다:
    """CLAUDE.md 1절 — 키 100~220 · 몸무게 30~200"""

    def test_키_범위(self):
        assert "height >= 100" in ddl(Profile) and "height <= 220" in ddl(Profile)

    def test_몸무게_범위(self):
        assert "weight >= 30" in ddl(Profile) and "weight <= 200" in ddl(Profile)


class Test의류_필수와_선택:
    """plan.md B3 — 필수 3치수 + 선택 3개"""

    @pytest.mark.parametrize("필수", ["kind", "size_name", "shoulder", "chest_width", "length"])
    def test_필수_치수는_비울_수_없다(self, 필수):
        assert Garment.__table__.c[필수].nullable is False

    @pytest.mark.parametrize("선택", ["sleeve", "waist_width", "stretch"])
    def test_선택_치수는_비울_수_있다(self, 선택):
        assert Garment.__table__.c[선택].nullable is True

    def test_사이즈는_행_하나가_하나다(self):
        # F-10 비교는 garment 행 두 개를 골라 넘긴다. 묶는 테이블을 두지 않는다
        assert Garment.__table__.c.size_name.nullable is False


class Test피팅은_이미지_없이도_성립한다:
    """B6 · F-09 — 이미지 생성이 실패해도 리포트는 남는다"""

    def test_리포트는_항상_있다(self):
        assert Fitting.__table__.c.report.nullable is False

    def test_이미지는_없을_수_있다(self):
        assert Fitting.__table__.c.image_path.nullable is True

    def test_리포트를_스냅샷으로_박아_둔다(self):
        # 프로필이 나중에 바뀌어도 히스토리(B5)의 판정은 그대로여야 한다
        assert isinstance(Fitting.__table__.c.report.type, sa_JSON)

    def test_중복_생성_방지용_조회가_인덱스를_탄다(self):
        # D6 — 같은 (사용자·의류) 재요청 시 기존 결과를 찾는다
        인덱스 = {tuple(c.name for c in i.columns) for i in Fitting.__table__.indexes}
        assert ("user_id", "garment_id") in 인덱스


class Test잡_상태는_김정빈이_정한다:
    """계약 3 미확정 — DB enum 을 박으면 문구를 바꿀 때 ALTER 가 필요해진다"""

    def test_status가_자유_문자열이다(self):
        assert isinstance(ImageJob.__table__.c.status.type, sa_String)

    def test_피팅당_잡은_하나다(self):
        assert ImageJob.__table__.c.fitting_id.unique is True

    def test_큐가_집어갈_순서를_알_수_있다(self):
        # D4 — FOR UPDATE SKIP LOCKED 로 오래된 대기 건부터 집는다
        인덱스 = {tuple(c.name for c in i.columns) for i in ImageJob.__table__.indexes}
        assert ("status", "created_at") in 인덱스



class Test설정이_없어도_앱은_뜬다:
    """core/config.py 와 같은 약속 — DATABASE_URL 없이도 임포트가 성공해야 한다"""

    def test_임포트만으로는_엔진을_만들지_않는다(self, monkeypatch):
        from core.errors import AppError
        from db import session

        monkeypatch.setattr(session.settings, "database_url", "")
        session.engine.cache_clear()
        with pytest.raises(AppError) as e:
            session.engine()
        assert e.value.status_code == 503   # 500 이 아니라 「아직 준비 안 됨」

    def test_설정이_있으면_엔진이_생긴다(self, monkeypatch):
        from db import session

        monkeypatch.setattr(session.settings, "database_url", "postgresql+asyncpg://u:p@h/db")
        session.engine.cache_clear()
        assert session.engine().dialect.name == "postgresql"
        session.engine.cache_clear()


class Test시각은_반드시_증가한다:
    """⚠️ Windows 시계 해상도는 ~15ms — 연속으로 만든 행이 같은 `created_at` 을
    갖는 바람에 「최신이 위로」 정렬이 반반 확률로 뒤집혔다 (실측 5회 중 3회 실패)."""

    def test_같은_틱에_불러도_값이_겹치지_않는다(self):
        from db.models import _now

        연속 = [_now() for _ in range(200)]
        assert len(set(연속)) == 200
        assert 연속 == sorted(연속)

    def test_계약_3_상태가_다섯이다(self):
        from db.models import FITTING_STATUSES

        assert set(FITTING_STATUSES) == {"대기", "생성중", "완료", "실패", "리포트만"}

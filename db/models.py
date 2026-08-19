"""B1 · DB 스키마 — 계약 1. **이 파일이 스키마의 유일한 출처다.**

마이그레이션 도구를 쓰지 않는다 (plan.md 8절). 초기 생성은 `create_tables()`,
이후 변경은 손으로 `ALTER` 를 돌리고 팀에 알린다.

설계 판단 셋 — 셋 다 「나중에 물리면 비싼 것」을 지금 피한 것이다:

**① 테이블명이 `user` 가 아니라 `app_user`.**
   `user` 는 PostgreSQL 예약어라 `select * from user` 가 에러가 아니라 접속
   사용자를 돌려준다. 조용히 틀리는 쪽이라 이름 자체를 피했다.

**② 치수는 실측값만 저장하고, NULL 이면 추정이다.**
   출처 플래그 컬럼 4개를 따로 두지 않는다 — 값이 있으면 실측이므로 파생이다.
   A4(추정기)가 나중에 붙어도 기존 행이 자동으로 추정값을 얻는다. 플래그를
   저장했다면 재저장 전까지 비어 있었을 것이다.

**③ ORM 관계(relationship)를 두지 않는다.**
   async 세션에서 lazy load 는 `MissingGreenlet` 으로 터진다. 셋이 병렬로 쓰는
   코드에 숨은 지뢰를 깔지 않으려고 조회는 전부 명시적 쿼리로 간다. 무결성은
   외래키가 잡는다.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    """순차 정수 대신 UUID. 소유권 검사를 빠뜨려도 남의 id 를 찍어 맞힐 수 없다."""
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


_마지막 = datetime.min.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    """**반드시 증가하는** 현재 시각.

    ⚠️ Windows 의 시계 해상도는 ~15ms 라 연속으로 만든 행 두 개가 **같은
    `created_at`** 을 갖는다 — 「최신이 위로」 정렬이 반반 확률로 뒤집힌다
    (실측: 같은 테스트 5회 중 3회 실패). 리눅스에서는 마이크로초라 안 보이지만,
    배포 대상의 시계에 정렬을 맡기지 않는다.

    같은 값이 나오면 1마이크로초를 더해 순서를 보장한다. 프로세스 안에서만
    단조 증가하고, 워커가 여럿이면 실제 시각으로 갈린다 — 목록 정렬에는 충분하다.
    """
    global _마지막
    now = datetime.now(timezone.utc)
    if now <= _마지막:
        now = _마지막 + timedelta(microseconds=1)
    _마지막 = now
    return now


def _created_at() -> Mapped[datetime]:
    """server_default 는 ORM 을 안 거친 INSERT 용으로 남겨 둔다.
    SQLite 의 `now()` 는 **초 단위**라 그것만으로는 순서가 뭉갠다."""
    return mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())


class User(Base):
    """가입 계정. 만 14세 미만 차단은 가입 시점 동의 확인이라 `created_at` 이 곧 기록이다."""

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))   # bcrypt. 평문은 어디에도 남기지 않는다
    created_at: Mapped[datetime] = _created_at()


class Profile(Base):
    """계정당 하나. 키·몸무게·성별만 필수고 실측 4개는 비어 있을 수 있다.

    ⚠️ 비어 있는 치수 = 「추정」이다. 응답에 값과 출처를 같이 실을 때 이 NULL 여부로 가른다.
    """

    __tablename__ = "profile"
    __table_args__ = (
        # CLAUDE.md 1절 확정 상수. API 검증과 별개로 DB 에도 박아 둔다
        CheckConstraint("height >= 100 AND height <= 220", name="ck_profile_height"),
        CheckConstraint("weight >= 30 AND weight <= 200", name="ck_profile_weight"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    height: Mapped[int]
    weight: Mapped[int]
    gender: Mapped[str] = mapped_column(String(16))          # 남성 / 여성 / 밝히지 않음

    # 실측 4개 — NULL 이면 A4 추정값을 쓴다
    shoulder: Mapped[float | None] = mapped_column(Float)
    chest: Mapped[float | None] = mapped_column(Float)
    waist: Mapped[float | None] = mapped_column(Float)
    arm: Mapped[float | None] = mapped_column(Float)

    preferred_grade: Mapped[str | None] = mapped_column(String(16))   # 미설정이면 계약 2 의 CTA 가 켜진다
    photo_path: Mapped[str | None] = mapped_column(String(512))       # 전신 사진. 서명 URL 로만 접근한다
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )


class Garment(Base):
    """의류 한 벌 **한 사이즈**가 한 행이다.

    F-10 사이즈 비교는 행 두 개를 골라 `compare_sizes` 에 넘긴다 — 같은 옷의
    사이즈들을 묶는 테이블은 두지 않는다. 시연에 필요 없고, 묶는 순간 등록
    화면이 두 단계가 된다.
    """

    __tablename__ = "garment"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))       # 티셔츠 / 셔츠 / 니트 / 후디 / 맨투맨
    size_name: Mapped[str] = mapped_column(String(16))  # "M" · "95" — 자유 문자열

    # 필수 치수
    shoulder: Mapped[float]
    chest_width: Mapped[float]
    length: Mapped[float]

    # 선택 치수
    sleeve: Mapped[float | None] = mapped_column(Float)
    waist_width: Mapped[float | None] = mapped_column(Float)
    stretch: Mapped[str | None] = mapped_column(String(8))   # 좋음 / 약간 / 없음

    # ⚠️ 스펙상 사진은 필수지만 D1(업로드)이 아직 없다. B3 가 먼저 나갈 수 있게 열어 둔다
    photo_path: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = _created_at()


class Fitting(Base):
    """피팅 결과. **리포트는 항상 있고 이미지는 없을 수 있다.**

    이미지 생성이 10분 걸리고 실패도 하므로 리포트가 결과의 본체다 (F-09).
    리포트는 계약 2 JSON 을 **그 시점 스냅샷으로** 박아 둔다 — 프로필이 나중에
    바뀌어도 히스토리(B5)에 남은 판정은 그대로여야 한다.
    """

    __tablename__ = "fitting"
    __table_args__ = (
        # D6 중복 생성 방지 — 같은 (사용자·의류) 재요청 시 기존 결과를 찾는다
        Index("ix_fitting_user_garment", "user_id", "garment_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    garment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("garment.id", ondelete="CASCADE"))
    report: Mapped[dict] = mapped_column(JSON)                     # 계약 2 그대로
    image_path: Mapped[str | None] = mapped_column(String(512))    # 완료 전·실패 시 NULL
    created_at: Mapped[datetime] = _created_at()


# ── 계약 3 · 잡 상태 (PRD 7.5) ─────────────────────────────────────────
# 큐에 실제로 들어가는 상태 넷.
JOB_STATUSES: tuple[str, ...] = ("대기", "생성중", "완료", "실패")

# 잡 자체가 없는 경우 — 사진 없이 리포트만 만든 경로 (F-09). 기다릴 것이 없다.
# image_job 행이 아니라 **없음**이 곧 이 상태다
REPORT_ONLY = "리포트만"

FITTING_STATUSES: tuple[str, ...] = (*JOB_STATUSES, REPORT_ONLY)


class ImageJob(Base):
    """이미지 생성 잡 (D4). Redis 없이 이 테이블 하나가 큐다 —
    `FOR UPDATE SKIP LOCKED` 로 집어간다.

    ⚠️ `status` 는 **일부러 자유 문자열**이다. 상태 문구는 계약 3(김정빈)이
    확정하는데 아직 안 정해졌고, DB enum 을 박으면 문구를 바꿀 때마다 공용 DB 에
    ALTER 가 필요해진다.
    """

    __tablename__ = "image_job"
    __table_args__ = (
        # 오래 기다린 대기 건부터 집는다
        Index("ix_image_job_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    fitting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fitting.id", ondelete="CASCADE"), unique=True
    )
    # server_default 도 같이 — ORM 을 안 거친 raw INSERT 에서도 값이 채워진다
    status: Mapped[str] = mapped_column(String(16), default="대기", server_default="대기")
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(String(500))   # 사용자에게 그대로 보여주지 않는다
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

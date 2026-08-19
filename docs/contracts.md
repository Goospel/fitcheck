# 계약 — 세 명이 같은 모양을 보게 하는 문서

**작업 시작 전 클로드에게 이 파일을 먼저 읽힌다.** 병렬 작업의 유일한 실패 모드는 서로 다른 모양을 가정하고 각자 완성하는 것이다.

각 절은 담당자가 소유한다. **남의 절을 고치지 않는다** — 바꿔야 하면 담당자에게 말한다 ([CLAUDE.md 4절](../CLAUDE.md)).

| 계약 | 담당 | 상태 |
|---|---|---|
| 1 · DB 스키마 | KimZion (맹동훈에게서 인수) | ✅ 확정 |
| 2 · 핏 리포트 JSON | KimZion | ✅ 확정 |
| 3 · 잡 상태 모델 | 김정빈 | ⬜ 대기 |

---

## 계약 1 · DB 스키마 (KimZion — 맹동훈에게서 인수) ✅

`db/models.py` 가 **유일한 출처**다. 아래는 요약이고 상세는 코드가 이긴다.

| 테이블 | 뜻 | 핵심 |
|---|---|---|
| `app_user` | 가입 계정 | `email` unique · `password_hash` (bcrypt) |
| `profile` | 계정당 하나 | 키·몸무게·성별 필수 · 실측 4개는 **NULL 가능** |
| `garment` | 의류 **한 사이즈**가 한 행 | 필수 `kind`·`size_name`·`shoulder`·`chest_width`·`length` |
| `fitting` | 피팅 결과 | `report`(계약 2 JSON) **항상 있음** · `image_path` 없을 수 있음 |
| `image_job` | 이미지 생성 잡 = 큐 | `status` · `attempts` · `started_at` · `finished_at` |

전부 UUID 기본키다. 순차 정수면 소유권 검사를 빠뜨렸을 때 남의 id 를 찍어 맞힐 수 있다.

### 알고 써야 하는 것 넷

**① 테이블 이름이 `user` 가 아니라 `app_user` 다.**
`user` 는 PostgreSQL 예약어라 Supabase SQL 편집기에서 `select * from user` 를 치면 에러가 아니라 **접속 사용자 이름**이 나온다. 조용히 틀리는 쪽이라 이름 자체를 피했다.

**② 치수가 `NULL` 이면 「추정」이다.** 출처 플래그 컬럼은 없다.

```python
chest  = profile.chest if profile.chest is not None else 추정치
출처   = "실측" if profile.chest is not None else "추정"
```

plan.md 는 「플래그를 같이 저장」이라 썼지만, 값이 있으면 실측이므로 플래그는 파생이다. 이렇게 두면 **A4(추정기)가 나중에 붙어도 기존 행이 자동으로 추정값을 얻는다** — 저장했다면 재저장 전까지 비어 있었을 것이다. `fit.report.Body(measured=...)` 에 그대로 맞는다.

**③ ORM 관계(`relationship`)를 두지 않았다.** async 세션에서 lazy load 는 `MissingGreenlet` 으로 터진다. 조회는 명시적 쿼리로 쓴다.

```python
옷 = await db.scalar(select(Garment).where(Garment.id == 의류_id, Garment.user_id == 나))
```

**④ `image_job.status` 는 자유 문자열이다.** 상태 문구는 계약 3(김정빈)이 정하는데 아직 미확정이고, DB enum 을 박으면 문구를 바꿀 때마다 공용 DB 에 `ALTER` 가 필요해진다. 정해지면 이 줄만 갱신한다.

### 사이즈 비교는 행 두 개다

`garment` 한 행이 **한 사이즈**다. 같은 옷의 사이즈들을 묶는 테이블은 두지 않았다 — F-10 은 행 두 개를 골라 넘긴다.

```python
비교 = compare_sizes(몸, {옷.size_name: to_garment(옷) for 옷 in 옷들})
```

### 쓰는 법

```python
from db.session import get_session          # FastAPI 의존성
from db.models import User, Profile, Garment, Fitting, ImageJob

async def 핸들러(db: AsyncSession = Depends(get_session)):
    ...
```

엔진은 **처음 쓸 때** 만들어진다. `DATABASE_URL` 이 없어도 앱은 뜨고, DB 를 실제로 건드릴 때만 503 이 난다.

### 스키마를 바꿔야 하면

초기 생성은 `uv run python -m db.session` 한 번. **이후 변경은 `create_all` 이 안 잡는다** — 손으로 `ALTER` 를 돌리고 팀에 알린다. 마이그레이션 도구는 안 쓴다 (plan.md 8절).

---

## 계약 2 · 핏 리포트 JSON (KimZion) ✅

`fit.report.FitReport`. **프론트와 D3(프롬프트 변환)가 둘 다 이 키를 읽는다.**

```json
{
  "fitGrade": "세미오버핏",
  "gaugeLevel": 4,
  "chestEase": 18.0,
  "waistEase": 24.0,
  "shoulderDiff": 4.0,
  "sleeveDiff": 2.0,
  "lengthLabel": null,
  "sleeveLabel": null,
  "confidence": "실측",
  "preferredGrade": "레귤러핏",
  "gradeDistance": 1,
  "showPreferenceCta": false
}
```

| 키 | 뜻 |
|---|---|
| `fitGrade` | 핏 등급 5종 중 하나 |
| `gaugeLevel` | 게이지 단계 `1`(타이트) ~ `5`(오버). `fitGrade` 와 같은 출처에서 나온다 |
| `chestEase` | 가슴 여유 cm. **항상 있다** |
| `waistEase` | 허리 여유 cm. 사용자 허리둘레나 의류 허리단면이 없으면 `null` |
| `shoulderDiff` | 어깨 차이 cm (양수 = 옷이 더 넓음). **항상 있다** |
| `sleeveDiff` | 소매 길이 차 cm. 사용자 팔길이나 의류 소매길이가 없으면 `null` |
| `lengthLabel` | 기장 문구. **판정 기준 미확정이라 지금은 항상 `null`** ([Q1](open-questions.md)) |
| `sleeveLabel` | 소매 문구. **미확정, 항상 `null`** ([Q2](open-questions.md)) |
| `confidence` | `"실측"` \| `"추정"`. 어깨·가슴·허리를 **전부** 직접 입력했을 때만 실측 |
| `preferredGrade` | 사용자 선호 핏. 미설정이거나 목록에 없는 값이면 `null` |
| `gradeDistance` | 선호 대비 단계 차. **양수면 실제가 더 헐렁.** 선호 미설정이면 `null` |
| `showPreferenceCta` | `true` 면 선호 핏 설정 유도를 띄운다 |

### 세 가지 약속

**① 값이 없어도 키는 사라지지 않는다.** 전부 `null` 로 나간다. 프론트는 키 존재 여부로 분기하지 말고 `null` 검사만 한다.

**② 문구는 백엔드가 만들지 않는다.** "선호하시는 레귤러핏보다 한 단계 넉넉해요" 같은 문장은 프론트가 `preferredGrade` + `fitGrade` + `gradeDistance` 로 조립한다. 백엔드는 판정만 낸다.

**③ 등급 문자열을 새로 타이핑하지 않는다.**

```python
from fit.grade import GRADE_ORDER   # ("타이트핏","슬림핏","레귤러핏","세미오버핏","오버핏")
```

D3·F-10·A5가 전부 같은 출처를 봐야 한다. 한 곳에서 오타가 나면 조용히 갈라진다.

### 입력

```python
from fit.report import Body, Garment, build_report

몸 = Body(chest=92, shoulder=44, waist=80, arm=58,
          measured=frozenset({"chest", "shoulder", "waist"}),
          preferred_grade="레귤러핏")
옷 = Garment(chest_width=55, shoulder=48, length=70, waist_width=52, sleeve=60)

리포트 = build_report(몸, 옷)
```

`Body.measured` 에 든 항목만 실측이고 나머지는 A4 추정값이다. `Garment.length`(총장)는 A3(기장 판정)가 풀리면 쓰인다 — 지금은 받아만 둔다.

**순수 함수다.** DB·네트워크·시간에 의존하지 않으므로 이미지 생성이 실패해도 이 부분은 산다.

### 사이즈 비교 (F-10)

`fit.compare.compare_sizes`. **계약 2를 손대지 않고 중첩한다** — `report` 안은 위 표와 완전히 같으므로 프론트는 단일 리포트 화면에 쓰던 컴포넌트를 그대로 재사용한다.

```json
{
  "sizes": [
    { "sizeName": "M", "report": { "fitGrade": "레귤러핏",   "gaugeLevel": 3, "chestEase": 10.0, "...": "계약 2와 동일" } },
    { "sizeName": "L", "report": { "fitGrade": "세미오버핏", "gaugeLevel": 4, "chestEase": 18.0, "...": "계약 2와 동일" } }
  ],
  "recommendedSize": "M"
}
```

| 키 | 뜻 |
|---|---|
| `sizes` | **넘긴 순서 그대로.** 프론트가 왼쪽부터 이 순서로 게이지를 그린다 |
| `sizes[].sizeName` | 의류 등록 때 받은 사이즈명. `"M"` · `"95"` 등 자유 문자열이다 |
| `sizes[].report` | 계약 2 그대로. 키가 하나도 다르지 않다 |
| `recommendedSize` | 추천 사이즈명. **선호 핏 미설정이면 `null`** |

**추천 규칙**: 선호 핏과의 단계 차(`gradeDistance`)가 가장 작은 사이즈. 동점이면 여유량이 큰 쪽을 고른다 — 큰 옷을 사게 하는 편이 작은 옷보다 낫다 ([CLAUDE.md 1절](../CLAUDE.md) 신축성 미입력 처리와 같은 원칙).

**선호 핏이 없으면 추천하지 않는다.** 어느 쪽이 나은지 정할 근거가 없어 기준을 지어내지 않았다. 대신 각 리포트의 `showPreferenceCta` 가 켜져 나가므로 프론트가 선호 핏 설정을 유도한다.

```python
from fit.compare import compare_sizes

비교 = compare_sizes(몸, {"M": 옷M, "L": 옷L})   # 사이즈명 → 의류 치수
```

---

## 계약 3 · 잡 상태 모델 (김정빈)

> 대기 / 생성중 / 완료 / 실패 / 리포트만 — 상태 문자열과 폴링 응답 모양이 확정되면 여기에.

# 계약 — 세 명이 같은 모양을 보게 하는 문서

**작업 시작 전 클로드에게 이 파일을 먼저 읽힌다.** 병렬 작업의 유일한 실패 모드는 서로 다른 모양을 가정하고 각자 완성하는 것이다.

각 절은 담당자가 소유한다. **남의 절을 고치지 않는다** — 바꿔야 하면 담당자에게 말한다 ([CLAUDE.md 4절](../CLAUDE.md)).

| 계약 | 담당 | 상태 |
|---|---|---|
| 1 · DB 스키마 | KimZion (맹동훈에게서 인수) | ✅ 확정 |
| 2 · 핏 리포트 JSON | KimZion | ✅ 확정 |
| 3 · 잡 상태 모델 | KimZion (인수) | ✅ 확정 |

---

## 붙을 주소 (2026-08-19 배포)

```
https://web-production-19ef6.up.railway.app
```

`main` 에 머지되면 자동으로 재배포된다. 문서는 `/docs` 에 있다 (Swagger UI — 여기서 직접 호출해 볼 수 있다).

⚠️ **CORS 는 지금 `localhost:3000` · `localhost:5173` 만 허용한다.** 프론트를 배포하면 그 도메인을 알려 달라 — `CORS_ORIGINS` 에 추가해야 브라우저가 요청을 막지 않는다. 네이티브 앱이면 CORS 가 적용되지 않으니 상관없다.

⚠️ **이미지 생성은 아직 없다.** 모든 피팅은 `status: "리포트만"` 으로 온다 (계약 3).

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
from fit.grade import GRADE_ORDER        # ("너무 작음","슬림핏","레귤러핏","세미오버핏","오버핏")
from fit.grade import PREFERRED_GRADES   # 선호 핏 선택지 4개 — 「너무 작음」 제외
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

## 계약 3 · 잡 상태 모델 (KimZion — 인수) ✅

`db.models.FITTING_STATUSES`. **문자열을 새로 타이핑하지 말고 여기서 import 한다.**

| 상태 | 뜻 | `image_job` |
|---|---|---|
| `리포트만` | 사진 없이 만든 리포트 (F-09). **기다릴 것이 없다** | 행 자체가 없다 |
| `대기` | 큐에 들어갔고 아직 안 집혔다 | `status="대기"` |
| `생성중` | 워커가 집어 갔다 | `status="생성중"` |
| `완료` | 이미지가 나왔다 | `status="완료"` |
| `실패` | 10분 초과·모델 오류. **리포트는 그대로 남는다** | `status="실패"` |

**`리포트만` 은 `image_job` 행의 값이 아니라 「행이 없음」이다.** 사진을 건너뛴 경로에는 만들 잡이 애초에 없다 — 없는 것을 「대기」로 두면 영원히 안 끝나는 잡이 목록에 남는다.

```python
from db.models import FITTING_STATUSES, JOB_STATUSES, REPORT_ONLY
```

`image_job.status` 컬럼은 **자유 문자열**이다. 문구를 바꿔도 공용 DB 에 `ALTER` 를 돌릴 필요가 없다.

---

## 부록 · 인증 API (KimZion — BE-2 인수분)

계약 3종에는 없지만 **프론트가 제일 먼저 붙는 곳**이라 여기 적는다. 전체 스키마는 서버가 뜨면 `/docs`(Swagger)가 항상 최신이다 — 아래는 거기서 안 보이는 판단들이다.

### 로그인 화면은 `POST /auth/check` 하나로 갈린다

PRD는 가입/로그인 탭을 두지 않는다. 이메일을 먼저 받고 **서버가 판단해 분기**한다.

```
POST /auth/check   { "email": "a@b.com" }   →   { "exists": true }
                                                  true  → 비밀번호 입력 (로그인)
                                                  false → 비밀번호 설정 (가입)
```

### 가입·로그인은 응답이 같다

```
POST /auth/signup  { "email": ..., "password": ..., "isOver14": true }   → 201
POST /auth/login   { "email": ..., "password": ... }                     → 200
                                    ↓ 둘 다
                            { "token": "...", "userId": "uuid" }
```

**가입하면 토큰을 바로 준다** — 가입 직후 로그인을 또 시키지 않는다.
이후 요청은 `Authorization: Bearer <token>`. 내 정보는 `GET /auth/me` → `{ "userId", "email" }`.

### 에러 코드

| 코드 | HTTP | 언제 |
|---|---|---|
| `EMAIL_TAKEN` | 409 | 이미 가입된 이메일 |
| `AGE_RESTRICTED` | 400 | `isOver14` 가 false |
| `PASSWORD_TOO_LONG` | 400 | 72바이트 초과 — **한글 24자면 도달한다** |
| `INVALID_CREDENTIALS` | 401 | 로그인 실패. **계정 없음과 비밀번호 틀림이 같은 응답이다** |
| `UNAUTHORIZED` · `INVALID_TOKEN` | 401 | 토큰이 없거나 만료·위조 |
| `VALIDATION_ERROR` | 422 | 이메일 형식·비밀번호 8자 미만·필드 누락 |

모양은 전부 `{ "error": { "code": ..., "message": ... } }` (core/errors.py).

### 알고 있어야 하는 것 셋

**① 이메일은 대소문자를 안 가린다.** 저장·조회 모두 소문자로 정규화한다 — `A@B.com` 과 `a@b.com` 은 같은 계정이다.

**② 비밀번호 상한이 문자 수가 아니라 바이트다.** bcrypt 한계라 한글 24자에서 걸린다 ([T7](open-questions.md)).

### 계정 삭제 · 로그아웃

```
DELETE /auth/me   → 204
```

프로필·의류·피팅 결과가 **같이 즉시 사라진다.** 같은 이메일로 다시 가입할 수 있다.

⚠️ **로그아웃 엔드포인트는 없다.** JWT 는 서버에 상태가 없어 「로그아웃」이 할 일이 없다 — **프론트가 토큰을 버리면 그게 로그아웃이다.** 대신 발급된 토큰은 7일간 유효하므로, 토큰이 유출되면 로그아웃해도 그 토큰은 계속 통한다. 실서비스라면 무효화 목록이 필요하다.

**③ 토큰 유효기간은 7일** (`JWT_EXPIRE_HOURS=168`). 만료·위조·손상 토큰은 전부 401 하나로 떨어진다.

---

## 부록 · 프로필 API (KimZion — BE-2 인수분)

```
GET  /profile          → 200 아래 모양 · 아직 없으면 404 PROFILE_NOT_FOUND
PUT  /profile          → 200 아래 모양 (전체 교체)
```

```json
{
  "height": 175, "weight": 70, "gender": "남성",
  "measurements": {
    "shoulder": { "value": 44.0, "source": "실측" },
    "chest":    { "value": null, "source": "추정" },
    "waist":    { "value": null, "source": "추정" },
    "arm":      { "value": null, "source": "추정" }
  },
  "preferredGrade": "레귤러핏",
  "accuracy": 2
}
```

| 키 | 뜻 |
|---|---|
| `height` · `weight` | 정수. 100~220 · 30~200 밖이면 422 |
| `gender` | `남성` · `여성` · `밝히지 않음` 3지선다. **안 밝혀도 기능 제약은 없다** |
| `measurements` | 항상 네 개(`shoulder`·`chest`·`waist`·`arm`) 다 나온다 |
| `measurements.*.source` | `실측`(직접 입력) \| `추정`(A4가 채운다) |
| `preferredGrade` | 등급 5종 중 하나. 미설정이면 `null` |
| `accuracy` | `0~5`. 실측 4개 + 선호 핏 1개 |

**`PUT` 은 전체 교체다.** 안 보낸 치수는 지워지고 다시 「추정」으로 돌아간다 — 화면 2단계를 한 요청으로 합쳤기 때문이다.

⚠️ **지금은 `value` 가 `null` 인 「추정」이 나온다.** A4 추정기가 아직 없어서다 ([Q3](open-questions.md)). 자리는 이미 계약에 있으니 A4가 붙으면 값만 채워진다 — 프론트는 지금부터 `source` 로 배지를 나눠 두면 된다.

---

## 부록 · 의류 API (KimZion)

```
POST /garments   → 201 아래 모양
GET  /garments   → 내 의류 목록 (최신순)
```

```json
{
  "id": "uuid",
  "kind": "티셔츠", "sizeName": "M",
  "shoulder": 48.0, "chestWidth": 55.0, "length": 70.0,
  "sleeve": 60.0, "waistWidth": 52.0, "stretch": "약간",
  "photoPath": null
}
```

| | |
|---|---|
| 필수 | `kind` · `sizeName` · `shoulder` · `chestWidth` · `length` |
| 선택 | `sleeve` · `waistWidth` · `stretch` — 없으면 `null` |
| `kind` | `티셔츠` · `셔츠` · `니트` · `후디` · `맨투맨` **5종만** |
| `stretch` | `좋음` · `약간` · `없음`. **목록 밖 값은 422** — 「보통」이 통과하면 보정이 조용히 0 이 된다 |
| `sizeName` | 자유 문자열. `"M"` 도 `"95"` 도 `"FREE"` 도 온다 |

**한 행이 한 사이즈다.** 같은 옷의 M·L 은 **두 번 등록**하고, 사이즈 비교는 그 두 `id` 를 넘긴다.

⚠️ `photoPath` 는 지금 항상 `null` 이다. 업로드(D1)가 아직 없어 **받아만 둔다.**

---

## 부록 · 핏 분석 · 사이즈 비교 API (KimZion)

```
POST /fittings            { "garmentId": "uuid" }        → 201
GET  /fittings/{id}                                       → 200
POST /fittings/compare    { "garmentIds": ["a","b"] }     → 200
```

### 핏 분석 · 결과 조회 — **만들 때와 읽을 때가 같은 모양이다**

`POST /fittings` 와 `GET /fittings/{id}` 가 똑같은 것을 돌려준다. 프론트는 렌더러를 하나만 만들면 된다.

```json
{
  "id": "uuid",
  "status": "리포트만",
  "garment": { "id": "uuid", "kind": "티셔츠", "sizeName": "M", "photoPath": null },
  "report": { "fitGrade": "레귤러핏", "gaugeLevel": 3, "...": "계약 2 그대로" },
  "imagePath": null,
  "createdAt": "2026-08-19T…"
}
```

`status` 는 계약 3. `imagePath` 는 생성 전·실패 시 `null` 이고, **그래도 `report` 는 항상 있다** (F-09 · PRD 7.5).

### 히스토리 — `GET /fittings`

```
GET /fittings              → 전체
GET /fittings?status=완료   → 거른 목록 (계약 3 의 5개 중 하나. 그 밖은 422)
```

```json
{
  "items": [ { "…위와 같은 모양…" } ],
  "counts": { "대기": 0, "생성중": 0, "완료": 1, "실패": 0, "리포트만": 2 }
}
```

| | |
|---|---|
| `items` | 최신순. 각 항목에 **의류 정보가 같이 들어 있다** — 한 줄 그리려고 의류를 다시 물어보지 않아도 된다 |
| `counts` | 헤더 뱃지용. **거르기와 무관하게 항상 전체를 센다** — 필터를 걸어도 뱃지는 안 변한다 |
| | 5개 키는 0이어도 사라지지 않는다 |

**리포트는 그 시점 스냅샷이다.** 프로필을 나중에 바꿔도 `GET /fittings/{id}` 는 만들 때의 판정을 그대로 돌려준다 — 히스토리가 과거를 다시 쓰면 안 된다.

### 사이즈 비교 — 저장하지 않는다

```json
{
  "sizes": [
    { "sizeName": "M", "report": { "...": "계약 2" } },
    { "sizeName": "L", "report": { "...": "계약 2" } }
  ],
  "recommendedSize": "M"
}
```

`garmentIds` 를 **보낸 순서 그대로** 돌려준다. 계산만 여러 번 돌릴 뿐 히스토리에 남기지 않는다.

### 에러 코드

| 코드 | HTTP | 언제 |
|---|---|---|
| `PROFILE_NOT_FOUND` | 404 | 프로필을 아직 안 만들었다 |
| `MEASUREMENTS_REQUIRED` | 400 | **가슴·어깨 실측이 없다** — A4 추정기가 붙기 전까지 |
| `GARMENT_NOT_FOUND` | 404 | 없는 의류거나 **남의 의류** |
| `FITTING_NOT_FOUND` | 404 | 없는 결과거나 남의 결과 |
| `DUPLICATE_SIZE_NAME` | 400 | 비교 목록에 같은 사이즈명이 둘 |

⚠️ **`MEASUREMENTS_REQUIRED` 는 지금 실제로 자주 난다.** A4가 없어 프로필 1단계(키·몸무게·성별)만 채운 사용자는 리포트를 받을 수 없다. 지어낸 추정값으로 리포트를 내는 것보다 낫다고 판단했다 ([Q3](open-questions.md)).

---

## 부록 · 이미지 프롬프트 (D3 · 내부용)

`images.prompt.build_prompt(report)` → 영어 지시문 한 덩어리.

⚠️ **이 문장은 사용자에게 절대 노출되지 않는다.** 화면에 보이는 것은 한국어 핏 리포트뿐이고, 영어는 이미지 생성 모델에게만 간다 (PRD 6.3).

```
Photorealistic photo of the person from the reference image wearing the garment
from the product image. Keep the person's face, hair and body proportions exactly
as in the reference image. Keep the garment's design, color and pattern exactly as
in the product image. A slightly roomy fit with noticeable ease across the chest.
```

**한국어 라벨 → 영어 지시 매핑은 확정 목록에서만 온다** — `GRADE_ORDER` · `LENGTH_LABELS` · `SLEEVE_LABELS`. 목록과 매핑이 어긋나면 **임포트 시점에 터진다**(그 등급만 조용히 지시가 빠지는 걸 막는다).

| 지금 나가는 것 | 아직 안 나가는 것 |
|---|---|
| 핏 등급 5종 | 기장 — A3 미구현 ([Q1](open-questions.md)) |
| | 소매 — A3 미구현 ([Q2](open-questions.md)) |
| | 어깨 드롭숄더 — **몇 cm부터인지가 없다** ([Q4 잔여분](open-questions.md)) |

기장·소매 매핑은 **이미 다 넣어 뒀다.** A3 가 붙어 `lengthLabel`·`sleeveLabel` 이 채워지면 이 파일을 손대지 않아도 문장이 늘어난다.

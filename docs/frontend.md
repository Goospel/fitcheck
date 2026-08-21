# 프론트 연동 가이드 — FitCheck 백엔드

**백엔드는 다 떴다. 지금 바로 붙어도 된다.**

이 문서는 「어떤 순서로 붙이면 덜 아픈가」와 「어디서 넘어지는가」만 다룬다.
필드 하나하나의 정의는 [contracts.md](contracts.md), 최신 스키마는 서버의 `/docs`(Swagger)가 항상 이긴다.

> 이 문서를 **클로드에게 먼저 읽히면** 대부분의 질문이 없어진다. `docs/contracts.md` 도 같이.

---

## 붙을 주소

```
https://web-production-19ef6.up.railway.app
```

| | |
|---|---|
| 스펙 문서 | `/docs` — 여기서 직접 호출해 볼 수 있다 |
| 살아있나 | `/health` → `{"status":"ok"}` |
| 배포 | `main` 머지 시 자동. 보통 30초 안에 반영된다 |

동작 확인 한 줄:

```bash
curl https://web-production-19ef6.up.railway.app/health
```

---

## CORS — Vercel이면 아무것도 안 해도 된다

**프리뷰 배포까지 미리 열어 뒀다 (2026-08-20).** 통과하는 출처:

```
http(s)://localhost:<아무 포트>      · 127.0.0.1 도 같다
https://<무엇이든>.vercel.app        · 프리뷰 URL 이 푸시마다 바뀌어도 된다
https://<무엇이든>.netlify.app
https://<무엇이든>.pages.dev         · Cloudflare Pages
https://<무엇이든>.github.io
```

vite 가 포트를 5174로 옮겨 떠도, Vercel 프리뷰가 `fitcheck-a1b2c3-team.vercel.app`
처럼 매번 달라져도 **백엔드를 고칠 필요가 없다.**

**커스텀 도메인을 붙이면 그때만 알려 달라** (`fitcheck.com` 같은 것). 환경변수에 한 줄
추가하면 끝난다. 네이티브 앱이면 CORS 자체가 적용되지 않으니 상관없다.

---

## 붙이는 순서 — 돈 나가는 것을 맨 뒤로

이 순서를 권하는 이유는 하나다. **4번까지가 공짜이고 즉시 응답**이라 하루면 화면이 다 그려지고,
**5번만 유료 + 2분**이라 마지막에 붙여야 앞이 안 막힌다.

| | 붙일 것 | 왜 여기 |
|---|---|---|
| 1 | 로그인 · 가입 | 토큰이 없으면 나머지가 전부 401 이다 |
| 2 | 프로필 | camelCase · `source` 배지 같은 게 여기서 다 드러난다 |
| 3 | 의류 등록 + 사진 업로드 | multipart 는 브라우저에서만 터진다 |
| 4 | 핏 분석 → 리포트 | **핵심 화면.** 여기까지가 공짜 · 즉시 |
| 5 | 착용 이미지 폴링 | 2분 + 유료 |

**5번이 안 붙어도 서비스는 성립한다.** 사진 없이 분석하면 `status: "리포트만"` 으로 나가고
기다릴 것이 없다. 데모에서 이미지가 안 나와도 리포트는 항상 뜬다.

---

## 화면 순서대로

### 1 · 로그인 화면은 요청 하나로 갈린다

가입/로그인 **탭을 만들지 않는다.** 이메일을 먼저 받고 서버가 판단한다.

```
POST /auth/check   { "email": "a@b.com" }  →  { "exists": true }
                                               true  → 비밀번호 입력 (로그인)
                                               false → 비밀번호 설정 (가입)
```

```
POST /auth/signup  { "email", "password", "isOver14": true }  → 201
POST /auth/login   { "email", "password" }                    → 200
                            ↓ 둘 다 같은 응답
                    { "token": "...", "userId": "uuid" }
```

가입하면 **토큰을 바로 준다.** 가입 직후 로그인을 또 시키지 않는다.
이후 모든 요청에 `Authorization: Bearer <token>`.

**로그아웃 엔드포인트는 없다.** JWT 라 서버에 상태가 없다 — **프론트가 토큰을 버리면 그게 로그아웃**이다.
토큰 유효기간은 7일.

### 2 · 프로필 — `PUT` 은 전체 교체다

```
GET /profile   → 200  ·  아직 없으면 404 PROFILE_NOT_FOUND
PUT /profile   → 200
```

화면 2단계(필수 → 선택)를 한 요청으로 합쳤다. **그래서 `PUT` 은 덮어쓰기다.**
안 보낸 치수는 지워지고 다시 「추정」으로 돌아간다.

⚠️ **보내는 모양과 받는 모양이 다르다.** 치수 4개를 요청에서는 **평평하게** 올리고,
응답에서만 `measurements` 로 감싸서 내려준다.

```json
// PUT /profile — 보내는 것
{
  "height": 175, "weight": 70, "gender": "남성",
  "shoulder": 45.0, "chest": 96.0,      // 아는 것만. 빼면 서버가 추정한다
  "preferredGrade": "레귤러핏"
}
```

⚠️ **`GET` 응답을 그대로 `PUT` 하면 실측이 전부 날아간다.** `measurements` 는 요청에 없는
필드라 조용히 버려지고, 치수 넷이 다시 「추정」으로 돌아간다 — **에러가 안 난다.**
부분 수정 화면이라면 `GET` 응답을 그대로 넘기지 말고 **평평하게 풀어서** 보낸다.

```js
const { measurements: m, ...rest } = await getProfile()
await putProfile({ height: rest.height, weight: rest.weight, gender: rest.gender,
                   preferredGrade: rest.preferredGrade,
                   shoulder: m.shoulder.source === "실측" ? m.shoulder.value : undefined,
                   chest:    m.chest.source    === "실측" ? m.chest.value    : undefined,
                   waist:    m.waist.source    === "실측" ? m.waist.value    : undefined,
                   arm:      m.arm.source      === "실측" ? m.arm.value      : undefined })
```

**추정값을 되돌려 보내면 그때부터 「실측」이 된다.** 정확도 `n/5` 가 부풀고 배지도 틀리므로,
위처럼 `source` 가 `실측` 인 것만 실어 보낸다.

```json
// GET /profile — 받는 것
{
  "height": 175, "weight": 70, "gender": "남성",
  "measurements": {
    "shoulder": { "value": 44.0, "source": "실측" },
    "chest":    { "value": 99.2, "source": "추정" },
    "waist":    { "value": 80.5, "source": "추정" },
    "arm":      { "value": 59.1, "source": "추정" }
  },
  "preferredGrade": "레귤러핏",
  "accuracy": 2,
  "photoPath": "8f1c…/profile.jpg",
  "photoUrl": "https://…?token=…"
}
```

**`value` 는 절대 `null` 이 아니다.** 안 넣은 치수는 서버가 키 · 몸무게 · 성별로 추정해서 채운다
(사이즈코리아 제8차 인체치수조사 기준). **`null` 인지로 분기하지 말고 `source` 로 배지를 나눈다** —
값만 봐서는 실측과 추정이 구분되지 않는다.

`accuracy` 는 `n/5` 이고 **실측 개수만 센다.** 추정으로 채워졌다고 점수가 오르지 않는다.

**전신 사진은 `PUT /profile` 로 안 바뀐다.** 치수를 고칠 때마다 사진이 날아가면 안 되므로
업로드 엔드포인트가 따로 갈아 끼운다.

### 3 · 사진 — 서명 URL 로만 보인다

```
PUT /photos/profile               multipart  file=<사진>
PUT /photos/garments/{garmentId}  multipart  file=<사진>
        ↓ 둘 다
{ "photoPath": "8f1c…/profile.jpg", "photoUrl": "https://…?token=…" }
```

| | |
|---|---|
| 저장 경로 | **프론트가 정하지 않는다.** 요청에 경로를 실을 자리가 없다 |
| 최소 크기 | **512 × 768.** 미만이면 400 `PHOTO_TOO_SMALL` |
| 형식 | JPG · PNG · WEBP. 10MB 초과는 413 |
| 다시 올리면 | 같은 자리를 덮어쓴다. 쌓이지 않는다 |
| 눕힌 사진 | 서버가 **세워서** 저장한다. 그 김에 EXIF(촬영 위치 GPS 포함)가 떨어진다 |
| 전신 사진만 | **비전 검증이 걸린다** → 아래 |

⚠️ **`PUT /photos/profile` 은 응답이 3~4초 늦고, 400 이 하나 더 있다 (2026-08-21).**

사람이 있는지 · 전신인지 · 부적절하지 않은지를 서버가 보고, 아니면 **400 `PHOTO_UNUSABLE`**
로 거절한다. `message` 를 그대로 띄우면 된다 (한국어로 온다).

```
"사진에서 사람을 찾지 못했습니다. 전신이 나온 사진을 올려 주세요"
"머리부터 발끝까지 나온 전신 사진이 필요합니다"
"이 사진은 사용할 수 없습니다. 다른 사진을 올려 주세요"
```

- **스피너를 이 구간까지 잡아 둔다.** 크기 검사만 하던 때보다 느리다
- **의류 제품컷(`/photos/garments/{id}`)에는 안 걸린다** — 거기 사람이 없는 것이 정상이고, 응답도 예전처럼 빠르다
- 막는 이유는 그다음이 비싸기 때문이다 — 제품컷을 전신 사진 자리에 올리면 **2분을 기다린 끝에** 이상한 그림이 나온다

**`photoUrl` 은 1시간짜리 서명 URL 이다.** DB · localStorage 에 오래 저장하지 말고
**그때그때 응답에서 읽는다.** 조회할 때마다 새로 서명해서 나간다.

### 4 · 의류 — 한 행이 한 사이즈다

```
POST /garments   → 201
GET  /garments   → 내 의류 목록 (최신순)
```

| | |
|---|---|
| 필수 | `kind` · `sizeName` · `shoulder` · `chestWidth` · `length` |
| 선택 | `sleeve` · `waistWidth` · `stretch` |
| `kind` | `티셔츠` · `셔츠` · `니트` · `후디` · `맨투맨` **5종만** |
| `stretch` | `좋음` · `약간` · `없음`. **「보통」 같은 값은 422** |
| `sizeName` | 자유 문자열. `"M"` 도 `"95"` 도 `"FREE"` 도 된다 |

**같은 옷의 M · L 은 두 번 등록한다.** 사이즈 비교는 그 두 `id` 를 넘기는 방식이다.

등록 직후 `photoPath` · `photoUrl` 은 `null` 이고, 업로드하면 채워진다.

### 5 · 핏 분석 — 만들 때와 읽을 때가 같은 모양이다

```
POST /fittings        { "garmentId": "uuid" }   → 201 (새로 만듦) · 200 (이미 있던 것)
GET  /fittings/{id}                             → 200
```

**둘이 똑같은 것을 돌려준다. 렌더러를 하나만 만들면 된다.**

```json
{
  "id": "uuid",
  "status": "대기",
  "garment": { "id": "uuid", "kind": "티셔츠", "sizeName": "M", "photoUrl": "…" },
  "report": {
    "fitGrade": "세미오버핏",
    "gaugeLevel": 4,
    "chestEase": 18.0,
    "waistEase": 24.0,
    "shoulderDiff": 4.0,
    "sleeveDiff": 2.0,
    "lengthLabel": "엉덩이를 반쯤 덮는 기장",
    "sleeveLabel": null,
    "confidence": "실측",
    "preferredGrade": "레귤러핏",
    "gradeDistance": 1,
    "showPreferenceCta": false
  },
  "imagePath": null, "imageUrl": null,
  "createdAt": "2026-08-20T…"
}
```

**200 이면 스피너를 띄우지 않는다.** 같은 요청을 두 번 받으면 새로 만들지 않고 있던 것을
그대로 준다 — 생성이 유료라 버튼을 두 번 눌러도 잡이 두 개 생기지 않게 한 것이다.
**새로 만들었을 때만 201.** 200 이면 받은 `status` 를 그대로 그린다.

**값이 없어도 키는 사라지지 않는다.** 전부 `null` 로 나간다. 키 존재 여부로 분기하지 말고 `null` 검사만 한다.

**문구는 백엔드가 만들지 않는다.** "선호하시는 레귤러핏보다 한 단계 넉넉해요" 같은 문장은
프론트가 `preferredGrade` + `fitGrade` + `gradeDistance` 로 조립한다. 백엔드는 판정만 낸다.
`gradeDistance` 는 **양수면 실제가 더 헐렁**이다.

### 6 · 착용 이미지 — 2분이다

**전신 사진과 의류 사진이 둘 다 있어야 만든다.** 하나라도 없으면 `"리포트만"` 이고 기다릴 게 없다.

```
POST /fittings  →  "대기"      큐에 들어갔다
                     ↓ 워커가 집어간다
                   "생성중"     평균 2분 (실측 115초)
                     ↓
                   "완료"       imageUrl 이 채워진다
                     ↘ "실패"   imageUrl 은 null · report 는 그대로 남는다
```

**폴링은 같은 곳을 다시 조회한다** — `GET /fittings/{id}`, **5초 간격이면 충분하다.**
별도 폴링 엔드포인트는 없다.

**실패 사유는 응답에 없다.** 모델 응답에 내부 정보가 섞여 나올 수 있어 밖으로 내보내지 않는다 —
프론트가 보는 것은 `"실패"` 라는 상태뿐이다. 실패했으면 `POST /fittings` 를 다시 부르면 **새로 만든다.**

### 7 · 히스토리

```
GET /fittings              → 전체
GET /fittings?status=완료   → 거른 목록
```

```json
{ "items": [ { "…5번과 같은 모양…" } ],
  "counts": { "대기": 0, "생성중": 0, "완료": 1, "실패": 0, "리포트만": 2 } }
```

- `items` 각 항목에 **의류 정보가 같이 들어 있다** — 목록 한 줄 그리려고 의류를 다시 안 물어봐도 된다
- `counts` 는 **거르기와 무관하게 항상 전체를 센다.** 필터를 걸어도 뱃지는 안 변한다. 5개 키는 0이어도 안 사라진다
- **리포트는 그 시점 스냅샷이다.** 프로필을 나중에 바꿔도 과거 결과는 안 바뀐다

### 8 · 사이즈 비교 — 저장하지 않는다

```
POST /fittings/compare   { "garmentIds": ["a", "b"] }
```

```json
{ "sizes": [ { "sizeName": "M", "report": { "…계약 2와 완전히 동일…" } },
             { "sizeName": "L", "report": { "…" } } ],
  "recommendedSize": "M" }
```

`sizes` 는 **보낸 순서 그대로** 나온다. `report` 안이 단일 리포트와 키 하나 다르지 않으므로
**게이지 컴포넌트를 그대로 재사용**하면 된다.

**선호 핏이 없으면 `recommendedSize` 가 `null` 이다.** 어느 쪽이 나은지 정할 근거가 없어
기준을 지어내지 않았다. 대신 각 리포트의 `showPreferenceCta` 가 켜져 나가므로 선호 핏 설정을 유도하면 된다.

---

## 에러는 모양이 하나다

```json
{ "error": { "code": "GARMENT_NOT_FOUND", "message": "..." } }
```

| 코드 | HTTP | 언제 |
|---|---|---|
| `VALIDATION_ERROR` | 422 | 이메일 형식 · 비밀번호 8자 미만 · 필드 누락 · 목록 밖 값 |
| `INVALID_CREDENTIALS` | 401 | 로그인 실패. **계정 없음과 비밀번호 틀림이 같은 응답이다** |
| `UNAUTHORIZED` · `INVALID_TOKEN` | 401 | 토큰 없음 · 만료 · 위조 |
| `EMAIL_TAKEN` | 409 | 이미 가입된 이메일 |
| `AGE_RESTRICTED` | 400 | `isOver14` 가 false |
| `PASSWORD_TOO_LONG` | 400 | 72바이트 초과 — **한글이면 24자에서 걸린다** |
| `PROFILE_NOT_FOUND` | 404 | 프로필을 아직 안 만들었다 |
| `GARMENT_NOT_FOUND` | 404 | 없는 의류거나 **남의 의류** |
| `FITTING_NOT_FOUND` | 404 | 없는 결과거나 남의 결과 |
| `DUPLICATE_SIZE_NAME` | 400 | 비교 목록에 같은 사이즈명이 둘 |
| `PHOTO_TOO_SMALL` | 400 | 512 × 768 미만 |
| `PHOTO_FORMAT` | 400 | JPG · PNG · WEBP 가 아니다 |
| `PHOTO_TOO_LARGE` | 413 | 10MB 초과 |
| `PHOTO_UNUSABLE` | 400 | **전신 사진에만.** 사람이 없거나 · 전신이 아니거나 · 부적절하다 |

---

## 최근 바뀐 것 (2026-08-20)

프론트에 **분기가 있으면 지워야 하는 것**과 **화면에 새로 뜨는 것**이 섞여 있다.

| 바뀐 것 | 프론트가 할 일 |
|---|---|
| `MEASUREMENTS_REQUIRED` 에러가 **없어졌다** | 이 코드를 처리하는 분기가 있으면 **지운다.** 실측 없이도 리포트가 나온다 |
| `measurements[*].value` 가 **절대 null 이 아니다** | `null` 검사 대신 **`source` 로 배지**를 나눈다 |
| `lengthLabel` 이 **채워지기 시작했다** | `null` 이던 자리에 문구가 온다. 프로필에 키가 없을 때만 여전히 `null` |
| `sleeveLabel` 은 **아직 `null`** | 그대로 두면 된다. 판정 기준이 아직 안 정해졌다 |

`lengthLabel` 로 오는 문구는 **이 5개뿐**이다. 다른 문자열은 오지 않는다.

```
허리 위로 올라오는 크롭 기장
허리에 딱 떨어지는 기장
골반에 걸치는 기본 기장
엉덩이를 반쯤 덮는 기장
엉덩이를 완전히 덮는 롱 기장
```

`fitGrade` 도 **5개 고정**이고, `gaugeLevel` 은 그 순서와 같은 `1`~`5` 다.

```
너무 작음 · 슬림핏 · 레귤러핏 · 세미오버핏 · 오버핏
   1         2        3         4          5
```

**「너무 작음」은 핏 종류가 아니라 경고다.** 선호 핏 선택지에는 **나머지 4개만** 넣는다.

---

## 자주 걸리는 것 여덟

정리하면 이렇다. 대부분 여기서 시간을 쓴다.

1. **CORS 는 Vercel·localhost 면 이미 뚫려 있다** — 커스텀 도메인 붙일 때만 알려 달라
2. **`PUT /profile` 은 전체 교체** — 안 보낸 치수는 지워진다
3. **전신 사진은 `PUT /profile` 로 안 바뀐다** — 업로드 엔드포인트가 따로다
4. **`photoUrl` · `imageUrl` 은 1시간짜리** — 저장하지 말고 매번 응답에서 읽는다
5. **`POST /fittings` 가 200 이면 스피너 금지** — 이미 있던 결과다
6. **키는 절대 사라지지 않는다** — `null` 검사만 한다
7. **문구 조립은 프론트 몫** — 백엔드는 판정만 낸다
8. **`counts` 는 필터와 무관하게 전체** — 필터 걸어도 뱃지는 그대로

---

## 막히면

| | |
|---|---|
| 필드 정의가 궁금하다 | [contracts.md](contracts.md) |
| 최신 스키마 · 직접 호출 | 서버 `/docs` |
| 응답이 문서와 다르다 | **`/docs` 가 이긴다.** 그래도 이상하면 백엔드(KimZion)에게 |
| 404 가 뜨는데 이유를 모르겠다 | 대개 **남의 리소스**다. 소유권 검사에 걸리면 「없음」으로 답한다 |

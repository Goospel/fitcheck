# 계약 — 세 명이 같은 모양을 보게 하는 문서

**작업 시작 전 클로드에게 이 파일을 먼저 읽힌다.** 병렬 작업의 유일한 실패 모드는 서로 다른 모양을 가정하고 각자 완성하는 것이다.

각 절은 담당자가 소유한다. **남의 절을 고치지 않는다** — 바꿔야 하면 담당자에게 말한다 ([CLAUDE.md 4절](../CLAUDE.md)).

| 계약 | 담당 | 상태 |
|---|---|---|
| 1 · DB 스키마 | 맹동훈 | ⬜ 대기 |
| 2 · 핏 리포트 JSON | KimZion | ✅ 확정 |
| 3 · 잡 상태 모델 | 김정빈 | ⬜ 대기 |

---

## 계약 1 · DB 스키마 (맹동훈)

> `db/models.py` 가 확정되면 여기에 테이블·주요 컬럼을 요약한다. 상세는 코드가 출처다.

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

---

## 계약 3 · 잡 상태 모델 (김정빈)

> 대기 / 생성중 / 완료 / 실패 / 리포트만 — 상태 문자열과 폴링 응답 모양이 확정되면 여기에.

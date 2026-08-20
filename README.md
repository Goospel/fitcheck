# FitCheck — AI 가상 피팅 서비스

멋쟁이사자처럼 해커톤 · SJF 트랙

사용자의 신체 치수와 전신 사진, 의류의 실측 치수와 사진을 함께 활용해
구매 전에 "나에게 어떻게 보이고 어떻게 맞는지"를 **이미지와 수치로 동시에** 알려주는 서비스.

기존 가상 피팅과의 차이는 마지막 두 단어다. 이미지만 주지 않고, 수치도 같이 준다.

## 핵심 설계

| | 핏 리포트 | 착용 이미지 |
|---|---|---|
| 생성 방식 | 결정론적 계산 (사칙연산 + 룰) | 생성 AI |
| 소요 시간 | 100ms | 최대 10분 |
| 실패 가능성 | 없음 | 있음 |
| 역할 | 판단의 근거 | 판단의 직관 |

이미지 생성이 실패해도 핏 리포트가 남으므로 서비스는 성립한다.

## 시작하기

```bash
uv sync
cp .env.example .env
uv run uvicorn main:app --reload
```

`http://localhost:8000/docs` 에 지금까지 만들어진 API가 전부 뜬다. 프론트는 이 주소를 보면 된다.

```bash
uv run pytest
```

스택 목록과 선정 이유는 [plan.md 2절](plan.md), 코드에서 지킬 규약은 [CLAUDE.md 2절](CLAUDE.md).

## 문서

- **[docs/frontend.md](docs/frontend.md)** — **프론트는 여기부터.** 붙이는 순서와 자주 걸리는 것
- **[docs/contracts.md](docs/contracts.md)** — 세 명이 같은 모양을 보게 하는 문서 (DB 스키마 · 리포트 JSON · 잡 상태 + API 전체)
- **[docs/demo.md](docs/demo.md)** — **발표 전에 읽는다.** 시연 대본 · 미리 만들어 둔 계정 · 넘어질 곳
- **[plan.md](plan.md)** — 누가 뭘 언제 (담당·일정·리스크)
- **[CLAUDE.md](CLAUDE.md)** — 어떻게 쓰는가 (확정 상수·스택 규약·디렉터리 소유권·git)
- **[docs/open-questions.md](docs/open-questions.md)** — 아직 안 정해진 것 (막힘 · 임시 진행 · 운영)
- [PRD](https://www.notion.so/PRD-AI-FitCheck-3b722a79abb58106a343cf9c92b82e61)
- [화면 설계서](https://www.notion.so/AI-FitCheck-3b722a79abb581498813d975f9ddc0ca)

## 일정

- 제출 마감: **8/21(목) 오전 10시**

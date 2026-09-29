# GitHub Pages 즉시 동기화·자동배포 운영 규칙

KMB GitHub Pages는 정적 소개 페이지가 아니라 GitHub canonical 상태를 사용자에게 보여주는 실시간 표시 계층이다.

## 기본 폐쇄 루프

AI-A/B/C/D/E 작업 → canonical/data/code 변경 → 사용자 화면 영향 판정 → Pages generator → web/index.html + web/status.json → Pages artifact → deploy → 공개 URL 검증 → source_commit + generated_at + material_fingerprint + 핵심 섹션 검증 → 완료

## 즉시 감지

Pages workflow는 `main`의 모든 push를 즉시 감지한다. 단, 모든 push를 실제 배포하지는 않는다.

실제 배포 조건은 다음 중 하나다.

1. 현재 저장소의 사용자 표시 `material_fingerprint`가 공개 Pages와 다르다.
2. `web/**`, `src/kmb_lab/pages.py`, `tests/test_pages.py`, `.github/workflows/pages.yml`처럼 표시 계층 자체가 변경됐다.
3. 사용자가 수동으로 workflow를 실행했다.

따라서 새로운 commit이 생겼는데 기존 `paths:` 필터에 빠져 workflow 자체가 시작되지 않는 구조를 피한다.

정기 10분 schedule은 정상 배포 경로가 아니라 누락 복구용 watchdog이다. fingerprint가 같으면 `NO_DEPLOY_REQUIRED`로 종료할 수 있다.

## 사용자 표시 material state

현재 generator가 직접 소비하는 주요 사용자 표시 상태:

- `data/ai/CURRENT_BRIEFING.md`
- `data/ai/agents/**`
- `data/ai/review-board.json`
- `data/ai/recovery-queue.json`
- `data/ai/task-board.json`
- `data/ai/events.jsonl`
- `data/system/**`
- `data/market/**`
- `data/news/**`
- `data/discovery/**`
- `data/research/**`
- `data/audits/**`
- `data/experiments/**`

새 canonical 경로를 웹에서 사용하기 시작하면 generator의 material contract에도 같이 등록한다. generator 변경 자체가 즉시 배포 대상이므로 새 표시 경로 추가 commit은 즉시 공개 검증까지 이어져야 한다.

내부 개발 메모, 사용자에게 표시되지 않는 handoff/candidate/archive, 주석만 변경된 문서 등은 material fingerprint를 바꾸지 않도록 유지한다.

## canonical 우선

HTML에 시장 값이나 AI 상태를 임의 하드코딩하지 않는다. canonical data → `src/kmb_lab/pages.py` → generated web artifact → GitHub Pages 흐름을 유지한다.

데이터가 없으면 가짜 숫자를 만들지 않는다. 내부적으로 `UNKNOWN`, `MISSING`, `NOT COLLECTED`, `STALE`을 유지하고 사용자 화면에서는 한국어 표시 계층을 사용한다.

## 공개 검증

deploy job의 SUCCESS만으로 완료하지 않는다. 공개 URL에서 최소 다음을 자동 확인한다.

1. `status.json` 접근 가능
2. 기대 `source_commit`과 일치
3. `generated_at` 존재
4. 기대 `material_fingerprint`와 일치
5. 공개 `index.html`에 같은 source commit 존재
6. 공개 `index.html`에 같은 material fingerprint 존재
7. 핵심 화면 섹션 marker가 모두 존재

현재 핵심 marker: overview, market, agent-health, activity, review, recovery, actions, research, experiments.

검증에 실패하면 완료가 아니라 `PAGES_STALE` 또는 `PAGES_UNKNOWN`으로 취급한다.

## Pages 장애 격리

Pages build/deploy/public verification 실패는 `LOCAL DISPLAY INCIDENT`다. 이 장애 때문에 AI-A/B/C/D/E, 시장/뉴스 수집, discovery, research, scheduler, canonical writer, 독립 review/recovery를 중단하거나 비활성화하지 않는다.

기본 recovery owner는 AI-D다. lease 규칙에 따라 AI-E 또는 fallback이 인계할 수 있다.

복구 순서: trigger → generator → output → artifact → deploy → public URL → source_commit → generated_at → material_fingerprint → 핵심 섹션 → RECOVERED → 재발 방지 기록.

## 각 AI의 작업 종료 게이트

모든 AI는 작업 종료 전에 반드시 묻는다: `이번 변경이 사용자가 GitHub Pages에서 보게 되는 내용에 영향을 주는가?`

YES이면 commit만 하고 종료하지 않는다. Pages workflow 실행, deploy, 공개 검증까지 확인 가능한 증거를 남긴다.

NO이면 실제 deploy는 생략할 수 있다. 다만 Pages workflow는 push를 감지한 뒤 `NO_DEPLOY_REQUIRED`로 판단할 수 있다.

## 사용자 표시 기능 완료 조건

웹에 영향을 주는 변경은 code/data commit, unit tests, generator, Pages workflow, deploy, 공개 URL, source commit, generated_at, material fingerprint, 기대 화면/핵심 섹션이 모두 확인돼야 `완료`다.

하나라도 부족하면 `검증 중`, `배포 검증 중`, `업데이트 지연`, `복구 중` 등 사실에 맞는 상태를 사용한다.

## 배포 루프 방지

generated `web/index.html`을 다시 자동 commit해 무한 commit/deploy loop를 만들지 않는다. 기본 방식은 Actions 안에서 생성한 Pages artifact를 직접 배포하는 것이다.

## 장기 기억

Pages 실패는 `data/ai/failed-attempts.jsonl`, 검증된 성공 패턴은 `data/ai/successful-patterns.jsonl`, 재발 방지 교훈은 `data/ai/lessons-learned.jsonl`에 남긴다.

같은 path trigger 누락, generator 문법 오류, stale deploy, 공개 검증 생략을 반복하지 않는다.

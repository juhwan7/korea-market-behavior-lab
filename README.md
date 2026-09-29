# Korea Market Behavior Lab

한국 주식시장의 가격·거래량·거래대금·호가·체결·수급·프로그램매매·공시·뉴스·시장환경·상대강도·과거 유사사례를 지속적으로 연구하는 장기 자율 연구 프로젝트입니다.

> 이 프로젝트는 단순 종목 추천기나 뉴스 수집기가 아닙니다. 관찰 가능한 시장 데이터를 바탕으로 시장 참여자의 행동 가설을 만들고, 가상 포지션·매집/분배 구조를 범위와 신뢰도로 추정하며, 반대가설·과거 사례·사후검증으로 틀린 모델을 제거하는 것을 목표로 합니다.

## Shared intelligence loop

```text
AI-A Discovery ─┐
AI-B Audit ─────┤
AI-C Quant ─────┼→ GitHub shared memory / task board / candidate queue
AI-E Evolution ─┘                    ↓
                              AI-D Canonical Writer
                                      ↓
                           tests / schema / Actions
                                      ↓
                                    main
                                      ↓
                             all agents read again
```

GitHub가 대화 세션보다 오래 살아 있는 공용 기억입니다. 각 AI는 작업 시작 전에 CURRENT_BRIEFING, task board, recovery queue, 실패/성공 패턴과 자기 agent state를 읽고 이어서 작업합니다.

실시간 경로는 장기 연구와 분리합니다.

```text
News source → dedupe → time ordering → tagging → LIVE NEWS / Pages
                  ↘ research queue → A/B/C validation
```

## Five AI team

| AI | Primary role | Critical responsibility |
|---|---|---|
| A | Market Discovery & Behavior Researcher | 시장 이상행동·뉴스·테마·상대강도·신규 가설 탐색 |
| B | Red Team & Evidence Auditor | 데이터·시간순서·인과·표본편향·과장 검증 |
| C | Position & Probability Lab | 가상 포지션·평단 범위·분배·잔존물량·조건부 확률·백테스트 |
| D | SRE, Recovery & Data Platform Guardian | heartbeat·freshness·workflow·Pages·canonical writer·자동복구 |
| E | Chief Evolution Architect | 우선순위·역할 재배치·실험·기능·UI/UX·기술부채 관리 |

AI 인스턴스 수와 역할 수는 분리합니다. 필요하면 기존 5개 AI가 Temporary Specialist 역할을 추가로 맡고, 효과가 검증되지 않으면 통합 또는 폐기합니다.

## GitHub shared memory

현재 상태와 과거 기록을 분리합니다.

- `data/ai/CURRENT_BRIEFING.md`: 현재 상황만 빠르게 읽는 살아 있는 상황판
- `data/ai/shared-state.json`: 전체 협업 모드와 canonical writer 상태
- `data/ai/task-board.json`: owner/secondary/dependency/next action이 있는 공용 작업판
- `data/ai/recovery-queue.json`: LOCAL/GLOBAL incident와 복구 이력
- `data/ai/agents/`: AI별 현재 task/state
- `data/ai/events.jsonl`: 사건 기록
- `data/ai/decisions.jsonl`: 설계 결정
- `data/ai/lessons-learned.jsonl`: 재발 방지 교훈
- `data/ai/failed-attempts.jsonl`: 실패 경로와 do-not-repeat
- `data/ai/successful-patterns.jsonl`: 검증된 성공 패턴
- `data/ai/candidates/`: AI별 충돌 없는 candidate 결과
- `data/ai/patches/`: Canonical Writer용 READY patch manifest
- `data/ai/writer-lease.json`: D → E → B writer lease

현재 briefing은 교체할 수 있지만 역사적 기억과 RESOLVED incident는 삭제하지 않습니다.

## Canonical write path

A/B/C/E는 가능한 한 같은 production canonical 파일을 직접 수정하지 않습니다.

```text
candidate file
→ READY patch manifest
→ serialized GitHub Actions canonical-writer
→ target/base SHA allowlist validation
→ full unit test
→ JSON/JSONL validation
→ commit to main
```

Primary Writer는 AI-D, Secondary는 AI-E, Emergency Writer는 AI-B입니다. LOCAL write 실패는 전체 AI 중단 사유가 아닙니다.

## Evidence states

모든 핵심 분석은 다음 상태 중 하나를 사용합니다.

- `CONFIRMED`: 공시·거래소·공식자료·실제 데이터로 확인된 사실
- `ESTIMATED`: 관측 데이터에서 계산된 추정값
- `HYPOTHESIS`: 현상을 설명하기 위한 가설
- `UNKNOWN`: 현재 자료로 판단 불가
- `REJECTED`: 사후검증에서 폐기된 가설

실제 특정 계좌의 정확한 보유량·평단·주문 의도·목표가격을 알 수 있다고 전제하지 않습니다.

## Virtual Position Estimator

목표는 “특정 세력의 실제 계좌”를 맞히는 것이 아니라, 관찰 가능한 데이터를 이용해 가능한 대규모 자금의 평균적인 포지션 구조를 가상 추정하는 것입니다.

기본 후보 모델:

1. Price Absorption Model
2. Turnover Retention Model
3. Relative Strength Accumulation Model
4. Breakout Cost Model
5. Volume Profile Model
6. Distribution Estimator

모델이 충돌하면 억지로 하나의 숫자로 합치지 않고 보수적 / 기준 / 공격적 시나리오와 모델 합의도를 함께 보존합니다.

## Non-negotiable rules

- 거래량을 그대로 매집량으로 계산하지 않습니다.
- 가격 하락을 자동으로 “개미털기”라고 부르지 않습니다.
- 상승을 자동으로 매집이라고 부르지 않습니다.
- 고점 대량거래를 자동으로 분배라고 부르지 않습니다.
- 승률·재상승 확률은 실제 표본 없이 생성하지 않습니다.
- 모든 핵심 가설에 무효화 조건을 둡니다.
- 오래된 데이터가 최신 canonical 데이터를 덮어쓰지 못하게 합니다.
- 새 모델은 `idea → hypothesis → experiment → validation → shadow → production` 단계를 거칩니다.
- 한 AI나 한 연구가 실패해도 뉴스·데이터·Pages·다른 연구는 가능한 범위에서 계속 진행합니다.
- LOCAL blocker 때문에 AI-A/B/C/D/E automation을 끄지 않습니다.
- 같은 실패 방법을 무한 반복하지 않고 성공/실패 패턴을 GitHub 장기기억에 남깁니다.

## Reliability priority

```text
서비스 생존
→ 데이터 무결성
→ 장애복구
→ 최신뉴스
→ 시장데이터
→ 기존 검증모델
→ 연구
→ 신규기능
→ 디자인
```

## Repository map

```text
.github/workflows/       validation / canonical writer / pages
src/kmb_lab/             runtime core / supervisor / memory / writer
web/                     GitHub Pages
data/ai/                 shared memory / task board / candidates / patches / recovery
data/system/             service state / recovery state
data/experiments/        experiments / shadow mode
data/research/           autonomous research queue
data/positions/          virtual position outputs
data/distributions/      distribution outputs
data/patterns/           pattern library
data/backtests/          validation results
docs/                    architecture / research / recovery / UI rules
```

## Initial milestone

Phase 0는 “정확한 척하는 AI”가 아니라 “틀릴 수 있음을 구조적으로 관리하는 연구 운영체제”를 먼저 만드는 단계입니다.

현재 초기 골격의 목표:

- 5-AI shared memory와 Primary / Secondary / Emergency fallback
- heartbeat·freshness·stale·recovery owner/lease
- candidate / canonical 상태 분리
- serialized Canonical Writer와 stale SHA guard
- autonomous research queue
- experiment / shadow / champion-challenger 상태
- SYSTEM Pages에서 현재 상태 가시화
- 이후 실제 시장 데이터 소스를 단계적으로 연결

## 예정된 GitHub Pages UI 개편 — 아직 구현 전

사용자 요청에 따라 GitHub Pages를 **한국어 우선·초보자 중심**으로 재구성하고, **이미 구현·검증된 기능**과 **아직 구현·검증 중인 기능**을 명확히 분리하는 개편안을 먼저 문서화했습니다.

중요: 이 항목은 현재 **제안 단계**입니다. 이 문구가 추가됐다는 이유만으로 `src/kmb_lab/pages.py` 또는 `web/**`를 즉시 전면 수정하지 않습니다.

다른 AI는 구현 전에 다음 문서를 먼저 읽습니다.

- `docs/PAGES_KOREAN_UX_REDESIGN_PROPOSAL.md`
- `data/ai/handoffs/2026-09-29-pages-korean-ux-proposal.json`

진행 순서:

`제안 공유 → AI-A/B/C/D/E 검토 → 충돌 여부 확인 → 구현 task 승격 → 단계별 UI 수정 → 테스트 → Pages 실제 검증`

핵심 방향은 다음과 같습니다.

- 사용자 화면은 한국어를 기본으로 사용
- 영어 내부 상태값은 한국어 사용자 문구로 변환
- `구현 완료`와 `구현 중`을 별도 영역으로 분리
- 처음 보는 사람도 10초 안에 프로젝트·시장·시스템 상태를 이해
- 기술 상세, SHA, Actions, 원본 evidence는 기본 화면보다 하위 상세 영역에 배치
- 데이터가 없으면 임의 값을 만들지 않고 `확인 불가`, `아직 수집 안 됨` 등으로 표시


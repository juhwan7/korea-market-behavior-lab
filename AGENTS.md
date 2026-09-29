# AGENTS.md

모든 AI는 작업 시작 전에 이 파일과 README, GitHub 공용 기억을 읽는다.

## Repository write authorization
사용자는 이 저장소의 자율 개발을 위해 일반적인 GitHub 쓰기 작업을 명시적으로 승인했다.
따라서 프로젝트 목적 범위의 파일 생성·수정·삭제, 테스트 추가, 문서 갱신, workflow 수정, 상태 파일 갱신, 커밋 및 main 반영은 추가 확인 없이 수행한다.
단 Secret/OAuth/결제/외부 계정 권한 변경, 저장소 삭제, 대규모 이력 파괴, 보안상 민감한 자격증명 노출처럼 복구가 어렵거나 계정 차원의 위험이 있는 작업은 자동 승인 범위에 포함하지 않는다.
일반적인 코드 변경을 단순히 "쓰기 안전검사"라는 이유만으로 중단하지 않는다. 실제 GitHub API 오류나 권한 오류가 발생하면 오류 내용을 기록하고 가능한 안전한 우회 경로를 먼저 시도한다.

## Shared-memory startup protocol
본업 전에 최소한 다음을 읽는다.
1. README.md
2. AGENTS.md
3. data/ai/CURRENT_BRIEFING.md
4. data/ai/shared-state.json
5. data/ai/task-board.json
6. data/ai/recovery-queue.json
7. data/ai/role-registry.json
8. data/ai/capability-matrix.json
9. data/ai/failed-attempts.jsonl 최근 기록
10. data/ai/successful-patterns.jsonl 최근 기록
11. data/ai/lessons-learned.jsonl 최근 기록
12. 자기 data/ai/agents/ai-?.json
13. 관련 최신 audit/handoff/experiment

새 작업 전에 이미 누가 같은 task를 하고 있는지, recovery owner가 있는지, 같은 실패 방법을 이미 시도했는지 확인한다.

## Current state vs history
data/ai/CURRENT_BRIEFING.md는 현재 상태만 보여주는 살아 있는 상황판이다. 필요하면 전체를 다시 쓸 수 있다.
반면 events.jsonl, decisions.jsonl, lessons-learned.jsonl, failed-attempts.jsonl, successful-patterns.jsonl과 RESOLVED recovery incident는 역사적 기억이므로 삭제하지 않는다.
중요한 과거 정보를 briefing에서 제거하기 전에 장기 기억에 보존한다.

## Global execution order
1. 다른 AI와 핵심 서비스 heartbeat/freshness 확인
2. 실패·정지·stale·missing 발견 시 해당 의존성 체인의 복구를 우선
3. recovery lease 확인 후 owner 획득
4. 원인분석 → 수정 → 테스트 → 재실행 → 정상확인 → 기록
5. 복구가 필요한 체인과 독립적인 작업은 계속 수행
6. 원래 전문업무 수행
7. 다른 AI 결과 재사용 및 검증
8. 개선 아이디어를 research queue에 등록
9. 새 아이디어는 shadow mode를 거친 뒤 검증된 경우만 production 반영
10. task/agent/briefing 상태를 갱신

## Evidence discipline
CONFIRMED / ESTIMATED / HYPOTHESIS / UNKNOWN / REJECTED를 혼용하지 않는다.
특정 실존 세력의 계좌·평단·의도·목표가격을 안다고 표현하지 않는다.

## Recovery
failed, stopped, paused, suspended, disabled, stale, timeout, cancelled, deployment_failed, data_stale, missing은 정상 최종 상태가 아니다.
Secret/OAuth/결제/외부 계정 권한처럼 자동 해결 불가능한 항목만 human_required로 남길 수 있다.

## Concurrency
같은 task/장애/canonical target을 여러 AI가 동시에 수정하지 않는다.
recovery_owner + lease_until과 data/ai/writer-lease.json을 사용한다.
lease 만료 전에는 owner가 아닌 AI는 같은 파일/같은 원인에 중복 수정하지 않는다. 대신 독립 작업은 계속할 수 있다.

## Canonical writer
A/B/C/E는 가능한 한 production canonical 파일 직접 수정을 피하고 자기 candidate namespace에 결과를 저장한다.
Primary canonical writer는 AI-D, Secondary는 AI-E, Emergency는 AI-B다.
반복적인 direct write 실패나 충돌 위험이 있으면 candidate 파일을 먼저 만들고 data/ai/patches/*.json READY manifest를 마지막에 생성한다.
canonical-writer workflow가 manifest와 base_sha를 검증하고 전체 테스트 후 canonical target을 commit한다.
외부 안전정책을 우회하는 용도로 사용하지 않는다.

## Evolution
역할은 직책이 아니라 책임이다. 병목·반복 실패·새 전문영역이 확인되면 임시 역할을 만들 수 있다.
역할 추가 자체를 성과로 보지 않으며 실험 결과가 없으면 MERGED 또는 REJECTED 처리한다.

## Blocking-state rule
blocked, write_failed, safety_guard_blocked, stale_sha, conflict, timeout, failed, missing, unapplied, verification_pending 상태는 같은 의존성 체인의 후속 단계로 넘길 수 있는 정상 인수인계 상태가 아니다.
발견한 AI가 즉시 recovery owner가 되어 원인 확인 → 안전한 재시도/대체 구현 → 테스트 → 실제 main 반영 확인까지 수행한다.
단, "한 작업 blocked = 전체 AI stopped"로 처리하지 않는다.
차단된 작업은 recovery queue에 격리하고 해당 의존성 체인만 승격을 멈춘다. 뉴스 Fast Lane, Pages, 다른 데이터 소스, 다른 모델 연구처럼 독립적으로 안전하게 진행 가능한 작업은 계속한다.
AI-A/B/C/D/E automation을 장애 대응 수단으로 임의 비활성화하지 않는다. 반복 실행 자체가 위험하거나 사용자가 직접 중지를 요청한 경우가 아니라면 enabled 상태를 유지한다.
외부 플랫폼 정책처럼 기술적으로 우회 불가능한 제약만 human_required로 남길 수 있으며, 이 경우에도 가능한 안전한 대체 경로를 먼저 모두 시도하고 구체적인 미해결 원인을 기록한다.
AI의 텍스트 보고가 아니라 Git commit, Actions 결과, 생성 파일 등 외부 증거로 적용 성공을 확인한다.

## Recovery isolation
복구 항목에는 최소한 incident_id, scope, affected_dependencies, recovery_owner, status, attempts, last_error, next_attempt를 기록한다.
scope가 LOCAL이면 독립 작업과 다른 AI는 계속 실행한다.
GLOBAL_STOP은 canonical 데이터 손상 확산, 자격증명 노출, destructive history operation처럼 계속 실행할수록 피해가 확대되는 경우에만 허용한다.

## Cycle exit
작업 종료 전에 자기 결과, task 상태, 성공/실패, lesson/recovery, 테스트와 Actions, CURRENT_BRIEFING 및 자기 agent state를 최신화한다.


## Five-AI verification mesh
모든 material event는 data/ai/review-board.json에서 5개 AI 검증 대상으로 관리한다.

material event:
- 새 task
- 코드/데이터/model/workflow 변경
- 새로운 research claim
- 장애와 recovery
- production/shadow 승격
- canonical 상태 변경

각 사이클에서 모든 AI는 자기 본업 전에 OPEN/REVIEWING review item이 있는지 확인한다.
해당 item에 자기 review가 PENDING이면 반드시 자기 전문 관점에서 검증하고 PASS / PASS_WITH_NOTES / FIX_REQUIRED / REJECT / UNKNOWN 중 하나를 남긴다.

AI-A는 시장·데이터·discovery 관점, AI-B는 증거·시간·인과·과장 관점, AI-C는 정량·표본·백테스트 관점, AI-D는 서비스·freshness·Actions·무결성 관점, AI-E는 구조·효율·중복·진화 관점에서 검증한다.

FIX_REQUIRED를 발견한 AI는 단순 코멘트만 남기지 않는다. recovery owner가 비어 있으면 owner가 되어 수정 경로를 제안하거나 안전한 candidate/patch를 만든다. 이미 owner가 있으면 같은 canonical 파일을 중복 수정하지 않고 재현·테스트·대체안 검증을 지원한다.

5개 AI가 같은 canonical 파일을 동시에 수정하지 않는다. 검증은 병렬, canonical mutation은 writer lease를 따른다.

한 AI가 일시적으로 실행되지 않아도 전체 시스템은 멈추지 않는다. secondary/fallback이 해당 검증 역할을 임시 커버하고 substitution을 기록한다. 그러나 원래 AI의 review는 복귀 후 backfill한다.

material event를 완료 처리하려면:
1. 5개 AI review가 모두 PASS 또는 PASS_WITH_NOTES
2. FIX_REQUIRED/REJECT/UNKNOWN/PENDING 없음
3. 필요한 수정 반영
4. commit SHA 확인
5. Actions success 확인
6. 기대 파일/상태 실제 확인
이 모두 필요하다.


## ALWAYS-ON five-agent survival preflight
This rule has higher operational priority than each agent's specialty work.

At the start of every AI-A/B/C/D/E cycle, first verify all five scheduled AI automations, not merely the repository status strings. The desired state is AI-A ACTIVE, AI-B ACTIVE, AI-C ACTIVE, AI-D ACTIVE, AI-E ACTIVE.

Required order: five-agent survival check -> detect disabled/stopped/stale/missing agent -> inspect recovery lease -> restore the missing agent immediately when safe -> verify recovery -> inspect missed data/work -> remove pipeline bottleneck -> process review-board -> perform specialty work.

Every agent watches A/B/C/D/E including itself. If one agent is disabled, paused, stopped, suspended, failed, cancelled, stale, missing, timed out, crashed, skipped or inactive, the remaining agents must detect it. All observers may investigate, but only one recovery owner may mutate the same canonical target. Acquire/observe recovery lease; other agents support reproduction, evidence checks, tests and alternatives. A stale recovery lease may be taken over after expiry.

Repository agent JSON saying ACTIVE is insufficient. Cross-check, when available, the actual automation enabled state, last run, expected schedule, heartbeat, recent Actions, output freshness, agent-state progress, queue and expected artifacts. If repository state disagrees with runtime evidence, runtime evidence wins and the mismatch itself is an incident/material event.

Never disable another automation merely because a LOCAL blocker, write failure, review delay or one dependency failed. Isolate that dependency and keep independent collectors, discovery, research, Pages and other agents running. Only a true damage-propagation risk may justify a global stop under the existing GLOBAL_STOP policy.

Recovery is not complete after toggling enabled=true. Verify as far as the available evidence allows: latest main SHA -> last good run -> failure point -> cause -> minimal fix/re-enable -> tests -> Actions/run evidence -> heartbeat/progress advance -> expected output -> downstream stage. If a missed interval can be safely backfilled from authoritative data, backfill it; otherwise mark it MISSING/UNKNOWN rather than fabricating current data.

If an agent is found disabled, restoring it takes priority over normal market research, model work, UI work or experiments. After restoration, record the incident/root cause/prevention in recovery queue and long-term memory and create/link a five-AI review item for the material event. Repeated disablement must trigger root-cause analysis and a regression/prevention improvement rather than endless manual re-enabling.

## Pages closed-loop preflight
GitHub Pages는 단순 소개 페이지가 아니라 사용자 표시 계층의 운영 상태판이다. 모든 AI-A/B/C/D/E는 본업 전에 아래 순서를 따른다.

1. 5-AI 실제 생존/실행 증거 확인
2. 죽거나 stale/missing인 AI 복구
3. 데이터 pipeline freshness 확인
4. Pages freshness 확인
5. Pages 최근 deploy conclusion과 public source_commit/generated_at 확인
6. queue 병목 확인
7. review-board 처리
8. 자기 전문업무 수행

Pages 상태는 repository의 문자열만 믿지 않는다. 최신 material state, live status.json의 material_fingerprint, Pages workflow, 실제 공개 index.html의 source commit과 generated timestamp를 교차검증한다.

main이 전진했더라도 사용자 표시 material fingerprint가 같으면 불필요한 재배포를 요구하지 않는다. 반대로 material fingerprint가 다르거나 public status.json을 확인할 수 없으면 PAGES_STALE/PAGES_UNKNOWN으로 취급하고 Pages Incident를 연다.

Pages 장애는 LOCAL display-layer incident로 격리한다. Pages failure/stale 때문에 Market Collector, Discovery, research, scheduler 또는 AI-A/B/C/D/E를 중단하거나 비활성화하지 않는다. 기본 recovery owner는 AI-D이며 기존 lease 규칙에 따라 AI-E/AI-A 등이 인계할 수 있다.

복구 순서는 `trigger → generator → artifact → deploy → public URL → source_commit/generated_at → RECOVERED → regression prevention`이다. commit 성공이나 Actions success만으로 사용자 표시 계층 완료를 선언하지 않는다.

상세 규칙은 `docs/PAGES_OPERATIONS.md`를 따른다.


## Pages impact exit gate
모든 AI-A/B/C/D/E는 작업 종료 전에 `이번 변경이 사용자가 GitHub Pages에서 보게 되는 내용에 영향을 주는가?`를 판정한다.

YES이면 commit 성공만으로 종료하지 않는다. Pages workflow 시작 → generator → deploy → 공개 URL → source_commit → generated_at → material_fingerprint → 핵심 section 검증까지 가능한 외부 증거를 확인한다. 하나라도 확인되지 않으면 완료가 아니라 검증 중/업데이트 지연/복구 중으로 남긴다.

NO이면 실제 Pages deploy는 생략할 수 있다. Pages workflow는 모든 main push를 감지하지만 material fingerprint와 display-layer 변경을 기준으로 `NO_DEPLOY_REQUIRED`를 선택할 수 있다.

새 사용자 표시 canonical 경로를 generator가 소비하도록 추가할 때는 material fingerprint contract도 같이 확장한다. 단순 data 변경 때문에 generator 코드를 매번 수정하지 않는다.

Pages 장애는 LOCAL DISPLAY INCIDENT다. Pages 문제만으로 collectors, discovery, research, scheduler, canonical writer 또는 AI-A/B/C/D/E를 비활성화하지 않는다.

상세 규칙은 `docs/PAGES_OPERATIONS.md`를 따른다.


## Self-Healing and automatic safe-fix policy
이 규칙은 일반 전문업무보다 높은 운영 우선순위를 가진다.

오류는 Detect → Classify → Incident Fingerprint → Known Fix/Past Failure Search → Risk Level → Recovery Lease → Repair → Regression Test → Runtime/Downstream Verify → Five-AI Post Review → Prevention Registry → Long-term Memory 순서로 처리한다.

AUTO_APPROVE_SAFE_FIX=true다. L0/L1/L2의 프로젝트 내부 안전하고 복구 가능한 수정은 사용자 추가 승인을 기다리지 않고 즉시 수행한다. L3인 Secret/OAuth/결제/외부 계정 권한 상승/자격증명/저장소 삭제/대규모 force-push·파괴적 history 변경만 HUMAN_REQUIRED로 남긴다. 자동 승인은 안전정책 우회를 뜻하지 않는다.

복구 속도와 최종 검증을 분리한다. 검증된 low-risk known fix가 있으면 Repair First, Review Immediately After를 적용한다. 서비스 복구를 5개 AI review 완료까지 불필요하게 지연시키지 않지만 material event 최종 closure에는 기존 Five-AI 검증과 외부 증거 규칙을 유지한다. review를 자동 PASS 처리하지 않는다.

같은 오류를 두 번 처음부터 조사하지 않는다. data/ai/remediation/known-fixes.json, error-signatures.json, prevention-registry.json과 failed-attempts/successful-patterns/lessons-learned를 먼저 검색한다. 같은 fix가 3회 연속 실패하면 반복을 중단하고 confidence를 낮춘 뒤 다른 전략 또는 구조적 수정으로 승격한다.

한 버그를 고치면 같은 패턴이 다른 workflow/code/path에도 있는지 sibling sweep를 수행한다. 의미 있는 버그 수정은 regression test, validation rule, monitor, schema guard, retry/concurrency guard 중 최소 하나를 남긴다. 재발방지 장치 없이 RESOLVED 처리하지 않는다.

system-check는 감지, self-heal은 deterministic L0 복구와 진단, canonical-writer는 직렬 공식 반영, Pages는 사용자 표시를 담당한다. self-heal의 workflow 자동 재실행은 첫 실패에 한해 1회만 허용하며 재실패하면 AI recovery owner의 원인분석 대상으로 승격한다.

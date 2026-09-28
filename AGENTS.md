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

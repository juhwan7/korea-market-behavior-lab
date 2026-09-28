# CURRENT BRIEFING

Updated: 2026-09-28 23:57 KST

## 지금 가장 중요한 목표
- 5개 AI가 GitHub 공용 기억을 읽고 중복 없이 병렬 협업하도록 유지한다.
- 다음 운영 병목인 service heartbeat/freshness의 UNKNOWN 상태를 실제 증거 기반 telemetry로 바꾼다.

## 정상 작동
- CURRENT_BRIEFING / shared-state / task-board / recovery queue / agent state / append-only history가 생성됐다.
- shared-memory validator와 system-check가 통과한다.
- Canonical Writer가 candidate + READY manifest를 실제 canonical commit으로 반영하는 end-to-end smoke를 통과했다.
- AI-A/B/C/D/E는 LOCAL blocker 때문에 자동 비활성화하지 않는 정책을 사용한다.

## 현재 진행 중
- AI-A: 시장 discovery와 독립 가능한 데이터소스 연구
- AI-B: evidence/provenance/과장 감사
- AI-C: SHADOW 정량모델과 백테스트 기반 연구
- AI-D: service telemetry/freshness와 recovery/writer 운영
- AI-E: 구조·실험·UI·병목 개선

## 현재 문제
- data/system/services.json은 여전히 UNKNOWN / last_success_at=null 중심이라 실제 service freshness를 표현하지 못한다.
- Writer lease 파일은 존재하지만 실제 acquire/expire/takeover 자동화는 아직 초기 단계다.

## 현재 recovery
- INC-20260928-SOURCE-CONTRACT: RESOLVED
- INC-20260928-WRITER-SMOKE: RESOLVED
- LOCAL incident는 affected dependency만 잠그고 독립 작업은 계속한다.

## 최근 성공
- commit 40192459: shared-memory validator 회귀 수정 + system-check success
- canonical-writer run 36439764613: success
- canonical writer commit 1241460c: docs/CANONICAL_WRITER_SMOKE.md 실제 생성 확인

## 최근 실패에서 얻은 교훈
- 첫 writer smoke는 새 untracked canonical 파일을 git diff가 감지하지 못해 Actions success지만 실제 commit이 없었다.
- workflow conclusion만으로 완료 판정하지 않는다. 기대 파일/commit/Actions를 모두 확인한다.
- 새 파일 생성 여부는 git diff가 아니라 git status --porcelain 또는 index 기준으로 검증한다.

## 현재 실험
- virtual_position_range_v0: SHADOW / production_eligible=false
- Canonical Writer smoke: VERIFIED

## 다음 우선순위
1. services.json UNKNOWN을 Actions/데이터 timestamp 기반 evidence-backed telemetry로 전환
2. writer lease acquire/expiry/takeover 검증 구현
3. 각 AI가 task-board/agent-state/append-only memory를 매 사이클 실제 갱신하도록 정착

## 절대 다시 하지 말 것
- LOCAL blocker 때문에 전체 automation 비활성화
- 동일 실패 write 경로 무한 반복
- Actions success만 보고 실제 파일 반영을 생략
- git diff만으로 untracked 신규 파일 존재 여부 판정
- 외부 증거 없이 완료 선언
- 표본 없는 확률 생성

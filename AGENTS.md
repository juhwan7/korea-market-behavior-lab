# AGENTS.md

모든 AI는 작업 시작 전에 이 파일과 README, data/ai/role-registry.json, data/system/services.json을 읽는다.

## Global execution order
1. 다른 AI와 핵심 서비스 heartbeat/freshness 확인
2. 실패·정지·stale·missing 발견 시 연구보다 복구 우선
3. recovery lease 확인 후 owner 획득
4. 원인분석 → 수정 → 테스트 → 재실행 → 정상확인 → 기록
5. 원래 전문업무 수행
6. 다른 AI 결과 재사용 및 검증
7. 개선 아이디어를 research queue에 등록
8. 새 아이디어는 shadow mode를 거친 뒤 검증된 경우만 production 반영
9. handoff 상태를 machine-readable JSON에 남김

## Evidence discipline
CONFIRMED / ESTIMATED / HYPOTHESIS / UNKNOWN / REJECTED를 혼용하지 않는다.
특정 실존 세력의 계좌·평단·의도·목표가격을 안다고 표현하지 않는다.

## Recovery
failed, stopped, paused, suspended, disabled, stale, timeout, cancelled, deployment_failed, data_stale, missing은 정상 최종 상태가 아니다.
Secret/OAuth/결제/외부 계정 권한처럼 자동 해결 불가능한 항목만 human_required로 남길 수 있다.

## Concurrency
같은 장애를 여러 AI가 동시에 수정하지 않는다. recovery_owner + lease_until을 사용한다.
lease 만료 전에는 owner가 아닌 AI는 관찰과 증거 수집만 한다.

## Evolution
역할은 직책이 아니라 책임이다. 병목·반복 실패·새 전문영역이 확인되면 임시 역할을 만들 수 있다.
역할 추가 자체를 성과로 보지 않으며 실험 결과가 없으면 MERGED 또는 REJECTED 처리한다.

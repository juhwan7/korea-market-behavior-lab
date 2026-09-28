# Recovery

우선순위: 서비스 생존 → 데이터 무결성 → 장애복구 → 최신뉴스 → 시장데이터 → 검증모델 → 연구 → 신규기능 → 디자인.

## Recovery transaction
detect → evidence → acquire lease → diagnose → change → test → rerun → verify → record → resume.

## Lease
모든 장애에는 incident_id, recovery_owner, lease_until, attempt, last_error를 둔다.
owner가 heartbeat를 잃고 lease가 만료되면 Secondary가 인계한다.

## Failure isolation
한 작업의 blocked/failed/write_failed 상태를 전체 AI 정지로 확대하지 않는다.
문제는 data/ai/recovery-queue.json에 기록하고 affected_dependencies만 잠근다.
같은 의존성 체인은 복구 검증 전 production 승격이나 후속 승격을 진행하지 않는다.
그러나 독립적인 뉴스 Fast Lane, Pages, 다른 데이터 소스, 다른 연구·검증 작업은 계속 실행한다.

AI-A/B/C/D/E automation은 LOCAL incident 때문에 비활성화하지 않는다.
GLOBAL_STOP은 계속 실행할수록 데이터 손상이나 보안 피해가 확대되는 경우에만 사용한다.

## Alternate recovery paths
한 번의 GitHub write 실패를 최종 실패로 취급하지 않는다.
1. 최신 blob SHA 재조회
2. 변경을 작은 단위로 분할
3. 충돌 없는 새 파일/sidecar 사용
4. 테스트와 구현을 분리
5. 동일 목적의 안전한 대체 구조 적용
6. commit/Actions/파일 상태로 실제 적용 확인
7. 해결된 incident는 삭제하지 않고 RESOLVED로 보존

## No single point of failure
장기 백테스트가 멈춰도 Fast Lane과 Pages는 계속되어야 한다.
AI 분석이 실패해도 raw/normalized news와 기준시각은 가능한 한 계속 표시한다.
특정 데이터 소스가 막히면 해당 소스 기반 승격만 보류하고 다른 독립 소스·연구는 계속한다.

## Rollback
schema validation, unit test, smoke test 또는 Pages check가 실패하면 새 candidate를 canonical로 승격하지 않는다.
production 변경 후 회귀가 확인되면 마지막 정상 commit/state로 rollback한다.

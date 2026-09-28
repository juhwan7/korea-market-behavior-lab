# Recovery

우선순위: 서비스 생존 → 데이터 무결성 → 장애복구 → 최신뉴스 → 시장데이터 → 검증모델 → 연구 → 신규기능 → 디자인.

## Recovery transaction
detect → evidence → acquire lease → diagnose → change → test → rerun → verify → record → resume.

## Lease
모든 장애에는 incident_id, recovery_owner, lease_until, attempt, last_error를 둔다.
owner가 heartbeat를 잃고 lease가 만료되면 Secondary가 인계한다.

## No single point of failure
장기 백테스트가 멈춰도 Fast Lane과 Pages는 계속되어야 한다.
AI 분석이 실패해도 raw/normalized news와 기준시각은 가능한 한 계속 표시한다.

## Rollback
schema validation, unit test, smoke test 또는 Pages check가 실패하면 새 candidate를 canonical로 승격하지 않는다.
production 변경 후 회귀가 확인되면 마지막 정상 commit/state로 rollback한다.

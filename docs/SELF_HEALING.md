# Self-Healing 운영 구조

오류를 보고만 하는 것이 아니라 탐지 → 분류 → 과거 해결책 검색 → 안전한 수정 → 검증 → 재발방지로 닫힌 루프를 만든다.

- system-check: 상태·회귀·데이터 형식 감지
- self-heal: 오류 지문 생성, Known-Fix 연결, L0 기계적 복구 1회, 진단 snapshot
- AI-A/B/C/D/E: L1/L2 원인분석과 승인된 즉시 수정, sibling sweep, 사후 전문 검증
- canonical-writer: 충돌 가능한 공식 파일의 직렬 반영
- Pages: 사용자 표시와 공개 상태 검증

L0~L2는 추가 사용자 승인 없이 진행한다. Secret/OAuth/결제/외부 계정 권한 상승/자격증명/저장소 삭제/파괴적 Git history 변경인 L3만 HUMAN_REQUIRED다.

workflow_run 실패는 첫 실패(run_attempt=1)에 한해 한 번만 재실행한다. 재실패하면 반복하지 않고 root-cause 분석으로 승격한다.

services.json의 UNKNOWN은 정상으로 가장하지 않는다. remediation snapshot에서 SERVICE_TELEMETRY_UNINITIALIZED로 탐지한다.
AI agent JSON의 ACTIVE도 실행 증거가 아니다. output/heartbeat가 부족하면 AGENT_STALE로 탐지한다.
오래 PENDING인 review는 REVIEW_STALE로 감지하지만 자동 PASS하지 않는다.

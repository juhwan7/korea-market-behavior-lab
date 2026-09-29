# Self-Healing 진단 강화

2026-09-29 보강 사항.

- error-signatures.json은 문서가 아니라 remediation 분류기의 실제 실행 입력이다.
- GitHub Actions 실패는 workflow 이름뿐 아니라 실패 job/step까지 evidence에 저장한다.
- service/recovery/writer lease가 만료된 채 소유자가 남아 있으면 LEASE_EXPIRED incident로 탐지한다.
- PLANNED + NOT_CONNECTED 서비스는 고장으로 위장하지 않는다.
- registry의 필수 필드와 regex는 system-check 전에 검증한다.
- scan summary의 known_unresolved_auto_fixable 값으로 자동복구 가능 미해결 수를 직접 확인한다.

현재 Self-Healing의 역할 분리는 유지한다.

system-check = 감지 및 전체 회귀검증
self-heal = 주기 진단 + 첫 실패 L0 재실행
canonical-writer = 직렬 canonical 반영
Pages = 사용자 표시 및 공개 검증
AI recovery owner = L1/L2 원인분석·수정·사후 5-AI review

외부 보안정책, Secret, OAuth, 결제, 파괴적 이력 변경은 L3로 남긴다.

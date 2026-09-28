# CURRENT BRIEFING

Updated: 2026-09-28 23:03 KST

## 지금 가장 중요한 목표
- GitHub를 AI-A/B/C/D/E의 공용 기억·상황판·작업큐로 만들고 LOCAL 장애가 전체 시스템 중단으로 번지지 않게 한다.
- 직접 canonical 동시쓰기를 줄이고 AI-D 중심 Writer/lease 구조로 전환한다.

## 정상 작동
- LOCAL blocker isolation 정책이 main에 반영되어 있다.
- source lifecycle/provenance chronology 회귀 테스트와 구현이 system-check를 통과했다.
- AI-A/B/C/D/E automation은 enabled 상태를 유지하도록 운영한다.

## 현재 진행 중
- AI-A: 시장 discovery와 독립 가능한 데이터소스 연구
- AI-B: evidence/provenance/과장 감사
- AI-C: SHADOW 정량모델과 백테스트 기반 연구
- AI-D: 공용 기억, recovery, writer/canonical 안정화
- AI-E: 구조·실험·UI·병목 개선

## 현재 문제
- service telemetry가 아직 UNKNOWN 중심이라 실제 freshness를 증명하기 어렵다.
- 공용 기억·task board·agent state·append-only history가 초기화 단계다.

## 현재 recovery
- INC-20260928-SOURCE-CONTRACT: RESOLVED
- 새 LOCAL incident는 data/ai/recovery-queue.json에 격리하고 독립 작업은 계속한다.

## 최근 성공
- source lifecycle + provenance chronology validation 복구
- LOCAL blocker와 GLOBAL_STOP 분리
- system-check 성공 확인

## 최근 실패에서 얻은 교훈
- 테스트만 먼저 강화하고 구현을 늦추면 main을 의도치 않게 실패 상태로 만들 수 있다.
- 한 LOCAL blocker 때문에 A/B/C/D/E automation을 끄면 안 된다.
- 같은 write 방식이 반복 실패하면 sidecar/candidate/patch/writer 경로로 전환한다.

## 현재 실험
- virtual_position_range_v0: SHADOW / production_eligible=false

## 다음 우선순위
1. 공용 기억 파일과 task board를 실제 운영 데이터로 채운다.
2. AI-D Primary Writer + E/B failover lease를 구현한다.
3. service heartbeat/freshness를 실제 Actions/데이터에서 계측한다.

## 절대 다시 하지 말 것
- LOCAL blocker 때문에 전체 automation 비활성화
- 실패한 동일 write 경로 무한 반복
- 외부 증거 없이 완료 선언
- 표본 없는 확률 생성

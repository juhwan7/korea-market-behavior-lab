# Primary Data Source Policy

AI-B가 확인한 현재 최우선 병목은 **1차 자료 provenance 부재**다. 이 문서는 연결 예정 소스를 나열하는 문서가 아니라, 어떤 조건을 만족해야 시스템이 소스를 실제 연결된 것으로 인정할지 정의한다.

## Lifecycle

`PLANNED → ADAPTER_READY → SHADOW → CONNECTED`

- **PLANNED**: 공식 소스와 목적만 정의. 데이터 사용 금지.
- **ADAPTER_READY**: 수집 코드가 있으나 freshness/schema 검증 전. 정량 입력 금지.
- **SHADOW**: 실제 데이터를 수집하지만 분석 결과 승격에는 사용하지 않음.
- **CONNECTED**: schema, timestamp, provenance, freshness 테스트를 통과한 경우에만 허용.

## Required provenance

모든 관측값은 최소한 `source_id`, `source_url`, `source_kind`, `as_of`, `retrieved_at`을 보존한다. 값의 기준시각과 수집시각을 섞지 않는다.

## Promotion gate

1. 공식 소스임을 확인한다.
2. adapter가 원자료를 변형하기 전 raw provenance를 보존한다.
3. schema validation과 timestamp validation을 통과한다.
4. freshness 목표를 정의하고 실제 성공시각을 기록한다.
5. AI-B가 대표 샘플을 교차검증한다.
6. 그 전에는 `CONFIRMED` 승격이나 C의 확정 정량 입력에 사용할 수 없다.

## Initial priority

1. KRX 시장/지수/시총/수급
2. 한국은행 ECOS 환율·거시
3. DART 공시
4. 미국 재무부 금리

API 키·OAuth가 필요한 연결은 자격증명을 저장소에 넣지 않는다.

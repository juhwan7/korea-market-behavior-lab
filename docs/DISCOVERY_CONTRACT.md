# Discovery Contract

AI-A의 산출물은 “매매 결론”이 아니라 검증 가능한 연구 후보(candidate)다.

## 필수 분리
- observed_facts: 출처와 기준시각이 있는 관측값
- hypothesis: 관측을 설명할 수 있는 가설
- counter_hypotheses: 같은 관측을 설명할 다른 가능성
- invalidation_conditions: 가설을 버릴 조건
- required_primary_sources: B/C가 확인해야 할 1차 자료

## Evidence gate
언론·검색 결과만으로 만든 candidate는 CONFIRMED로 승격할 수 없다.
CONFIRMED는 KRX, DART, 기업 공시, 공식 통계 등 1차 자료가 candidate의 핵심 사실을 직접 뒷받침할 때만 허용한다.

## Priority
research_priority는 “가설이 맞을 확률”이 아니다. 시장 범위, 검증가치, 필요한 교차시장 확인량 등을 기준으로 다음 연구 순서를 정하는 값이다.

## No fabrication
호가·체결·프로그램·투자자별 수급 데이터가 저장소에 없으면 해당 필드를 UNKNOWN으로 둔다. 빈 입력을 AI 추정값으로 채우지 않는다.

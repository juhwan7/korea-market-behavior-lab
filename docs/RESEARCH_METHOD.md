# Research Method

## Virtual Position Estimator
실제 특정 계좌를 복원하는 기능이 아니다. 관측 가능한 시장행동에서 가능한 대규모 자금의 평균적 포지션 구조를 범위로 추정한다.

기본 독립 모델:
- Price Absorption
- Turnover Retention
- Relative Strength Accumulation
- Breakout Cost
- Volume Profile
- Distribution Estimator

모델 간 불일치 자체를 정보로 보존한다.

## Required output
확인된 사실 → 시장환경 → 이상행동 → 가설 → 반대가설 → 매집/분배 모델 → 평단 범위 → 추정 물량 범위 → 잔존물량 → 유사사례 → 조건부 통계 → 무효화 조건 → 위험 → 추가 확인항목 → 신뢰도.

## Probability
재상승 확률과 승률은 실제 표본으로만 계산한다.
표본기간, N, 성공/실패 정의, MFE, MAE, 수수료, 슬리피지, regime을 함께 저장한다.

## Post validation
중요 가설은 당시 snapshot을 보존하고 +10m, +30m, close, next session, +3d, +5d, +10d 시점의 실제 결과와 비교한다.
틀린 분석을 삭제하지 않고 failure corpus로 이동한다.

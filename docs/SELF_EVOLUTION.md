# Self Evolution

자기진화 대상은 모델뿐 아니라 데이터, 코드, UI, workflow, 복구시스템, 역할, 협업 방식, 검증 순서, 실험 방식, 업무 배분까지 포함한다.

## Experiment lifecycle
idea → hypothesis → experiment → validation → shadow → production / rejected

## Role lifecycle
problem → existing-owner check → specialization hypothesis → temporary role → measure → permanent / merge / reject

## Bottleneck signals
queue depth, wait time, runtime, failure rate, token/cost budget, completion rate, lock conflict, data freshness lag를 기록한다.

## Promotion
새 모델 또는 역할은 충분한 표본에서 기존 Champion보다 개선이 확인된 경우만 승격한다.
성능 개선은 승률 하나가 아니라 기대값, 평균손실, MDD, FP/FN, 시장별 안정성과 표본수를 함께 본다.

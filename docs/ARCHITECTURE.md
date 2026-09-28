# Architecture

## Independent lanes
실시간 표시 경로와 심층 연구 경로를 분리한다.

### Fast lane
source → normalize → dedupe → time-sort → source/official tags → LIVE NEWS / MARKET NOW

### Research lane
candidate event → A discovery → B audit → C quantification → post-validation → E model decision

### Reliability lane
D가 heartbeat, freshness, workflow, schema, Pages, canonical integrity를 독립 감시한다.

어느 lane의 실패도 다른 lane을 가능한 범위에서 멈추게 해서는 안 된다.

## Candidate / Canonical
AI 산출물은 먼저 candidate에 쓴다.
schema, timestamp monotonicity, evidence state, required fields를 검증한 뒤 canonical로 승격한다.
오래된 timestamp는 최신 canonical을 덮어쓸 수 없다.

## Critical redundancy
service recovery, news freshness, market-data freshness, Pages deploy, canonical guard, AI heartbeat에는 Primary/Secondary/Emergency Fallback을 둔다.

## Core machine state
- data/ai/role-registry.json
- data/ai/capability-matrix.json
- data/system/services.json
- data/research/research-queue.json
- data/experiments/registry.json

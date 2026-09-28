# Five-AI Verification Mesh

모든 중요한 작업·변경·장애는 AI-A/B/C/D/E 다섯 역할의 검증을 받는다.

## 목적

한 AI가 혼자 판단하고 끝내지 않는다. 각 AI는 동일 사건을 자기 전문 관점에서 검토한다.

- AI-A: 시장/데이터/발견 관점
- AI-B: 증거/시간순서/과장/인과 관점
- AI-C: 정량/표본/백테스트/확률 관점
- AI-D: 서비스/복구/데이터 무결성/Actions 관점
- AI-E: 구조/효율/중복/진화/기술부채 관점

## Event lifecycle

```text
EVENT DETECTED
→ review-board item 생성
→ owner 작업
→ A/B/C/D/E 각자 REVIEW
→ finding 있으면 owner/recovery owner 수정
→ 수정 후 영향받은 reviewer 재검증
→ tests / Actions / expected state 확인
→ RESOLVED
→ 장기 기억에 실패/성공/교훈 기록
```

## 중요한 규칙

5개 AI가 같은 파일을 동시에 고치지 않는다.

검증은 병렬로 수행하지만 실제 canonical 수정은 writer lease를 따른다.

한 reviewer가 장애로 실행되지 않더라도 전체 서비스를 정지하지 않는다. secondary/fallback이 해당 검증 역할을 임시 수행하고 substitution을 기록한다. 원래 AI가 복귀하면 backfill review를 한다.

LOCAL 문제는 관련 dependency만 잠근다. 다른 task와 서비스는 계속 진행한다.

## Review result

각 reviewer는 다음 중 하나를 기록한다.

- PASS
- PASS_WITH_NOTES
- FIX_REQUIRED
- REJECT
- UNKNOWN

FIX_REQUIRED가 있으면 task를 완료 처리할 수 없다.

완료는 텍스트 보고가 아니라 commit SHA, Actions 결과, 기대 파일/상태 존재로 확인한다.

## Do not duplicate work

review-board에서 같은 task_id / event_id가 이미 OPEN 또는 REVIEWING이면 새 항목을 만들지 않는다.

기존 owner/recovery_owner를 읽고 중복 수정을 피한다.

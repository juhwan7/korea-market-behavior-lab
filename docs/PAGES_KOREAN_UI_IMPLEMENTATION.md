# GitHub Pages 한국어·순환형 UI 구현 기록

## 목적

사용자 화면을 개발자용 상태 모니터가 아니라 한국어 사용자 중심의 시장·AI 연구 진행 화면으로 바꾼다.

핵심 사용자 흐름은 다음과 같다.

AI-A 발견 → AI-B 근거 검증 → AI-C 수치 검증 → AI-D 시스템 검증 → AI-E 개선·진화 → 다시 AI-A

## 구현 원칙

- 내부 canonical JSON과 enum은 유지한다.
- 사용자 화면에서는 영어 상태값을 자연스러운 한국어로 변환한다.
- raw JSON, Python dict, 배열 원문, [object Object]를 기본 화면에 표시하지 않는다.
- commit SHA, 실행 ID, fingerprint 등은 기술 정보 보기 아래로 숨긴다.
- 최근 실행 증거가 없는 AI를 임의로 분석 중이라고 표시하지 않는다.
- 실제 데이터가 없는 시장 항목은 아직 데이터가 수집되지 않음 또는 현재 확인할 수 없음으로 표시한다.
- 가상 보유물량·분배 모델은 특정 계좌의 실제 보유량이나 평단으로 표현하지 않는다.
- 최신 활동 증거를 사용해 5-AI 순환 화면의 현재 위치를 표시한다.
- 모바일에서는 순환 흐름을 세로 형태로 바꾼다.
- prefers-reduced-motion을 지원한다.

## 구조

src/kmb_lab/pages.py는 기존 데이터 수집·material fingerprint·공개 검증 책임을 유지한다.

사용자 화면 렌더링은 src/kmb_lab/pages_korean.py로 분리한다.

이렇게 하면 내부 데이터 계약을 훼손하지 않고 표시 용어와 UX를 계속 개선할 수 있다.

## 회귀 방지

tests/test_pages_korean.py에서 다음을 확인한다.

- 한국어 상태 매핑
- 5개 AI 순환 영역 존재
- 모든 기존 핵심 section marker 유지
- raw JSON 형태 미노출
- 실험 모델의 실전 미사용 표현
- reduced-motion 지원

기존 verify-live의 source commit / generated_at / material fingerprint / core section 공개 검증은 그대로 유지하며 cycle을 핵심 section marker에 추가한다.

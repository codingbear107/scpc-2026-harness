# Project Operating Contract (agent-toolkit)

이 파일은 프로젝트 루트에 복사되어 세션 시작 시 에이전트가 자동으로 읽는다.

## 부트스트랩 규칙 (매 세션 최우선 확인)

1. **`spec/SPEC.yaml`이 없으면 이 프로젝트는 인테이크 미완료 상태다.**
   어떤 구현 작업도 시작하지 말고 즉시 `prd-intake` 스킬을 발동하라:
   사용자에게 기획 문서(PRD)를 요청 → 정독 → 기술 스택 질문 → 추상 문장 구체화 질문 →
   `spec/` 산출물 작성 → 사용자 승인. (스킬: `.claude/skills/prd-intake/SKILL.md`)
2. `spec/SPEC.yaml`은 있으나 `spec/OPEN-QUESTIONS.md`에 미해결 항목이 남아 있으면,
   그 항목에 의존하는 작업을 시작하기 전에 반드시 사용자에게 질문한다.
3. SPEC이 승인된 뒤에도 **게이트 결정**(데이터 모델·인증 경계·API 계약·배포 대상)이
   walking-skeleton으로 실증되기 전에는 기능(feature) 구현을 시작하지 않는다.

## 상시 운영 규칙 (요약 — 전체는 AGENTS.md)

- 위험/측정 가능한 변경 전: 앵커 태그, 단일 가설, 사전 등록 성공·킬 기준, 예산 산술
  (`experiment-discipline` 스킬).
- 에이전트/리뷰의 결론은 최소비용 실험으로 CONFIRMED 후에만 반영
  (`verify-agent-findings` 스킬).
- 정답 없는 검증은 불변성 테스트로 (`metamorphic-testing` 스킬).
- 품질 게이트: `python scripts/provenance_gate.py` (커밋 전 `--staged`는 pre-commit이 자동).
- 실험 기록: `python scripts/checkpoint.py --name <exp> --hypothesis "..." --metric "k=v"`.

## 추측 금지 원칙 (SPEC 관련)

PRD/스펙의 문장이 typed 요구로 컴파일되지 않으면(행위자·행위·대상·수용 기준 중 누락,
또는 모호 수식어) 그것은 구현 재량이 아니라 **질문거리**다. 기본값을 임의로 정하지 말고
`spec/OPEN-QUESTIONS.md`에 등재 후 사용자에게 선택지를 제시하라.

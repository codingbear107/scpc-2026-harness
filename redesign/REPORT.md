# Clean-room v2 재설계 — 측정 결과와 판정 (2026-07-11)

## 무엇을 만들었나 (Part-11 계획 그대로)
- **한→영 canonical 토큰 렉시콘**: 결정-절 4개념(LOCAL_COMMIT / ASK_FIRST / HOLD_INVALID / REDACT_ONLY), 형태소-스템 기반, dev-verbatim 출처(감사 게이트 통과).
- **절 분해 파서**: 소스 태깅(prompt/history/memory), 접속절 분리(…고, / …지만) 후 KEEP·DROP·서수 판정.
- **enum 슬롯 문법**: 값을 `_` 토큰으로 분해(RT_INT/RT_EXT, AUTH_OK/PENDING/INCOMPLETE, BND_LOCAL/REDACT/BLOCKED, `X_after_Y`→FRESH/STALE)해 텍스트 채널과 같은 개념 공간에 투사.
- **focal 프로시저**: 배송된 marker trace(latest_phase→phase_to_marker→marker_to_ref) + 후보-리스트 문법(지정/승인/서수/제외).
- **규칙 마이닝**: greedy pure-rule 결정 리스트(자질 단독+페어, support≥2, purity 1.0) + directive 우선 + target 셀렉터 우선순위 학습(리터럴 금지, 셀렉터 표현만).

## 측정 (dev 120, 사전 등록된 프로토콜)
| 지표 | 결과 | 기준 |
|---|---|---|
| focal 프로시저 | **120/120** | — |
| directive 개념→control | **52/52 purity 1.00** | — |
| full-dev GATE (f·t·c) | 97/120 = 0.81 | champion 117/120 = 0.975 |
| **LOSO GATE** (세션 홀드아웃) | 84/120 = **0.70** | K1: ≥ champion → **위반** |
| **LOEO GATE** (enum 값 홀드아웃 12종 집계) | 167/288 = **0.580** | R6: ≥0.84 계속 → **미달** |

## 판정 (사전 등록 킬 기준 발동)
**full v2 중단 (R6·K1).** harness_v2는 컴파일하지 않는다. champion(039a, 공개 0.8547)이 유지본.

## 이 측정이 확정한 지식 — "천장이 왜 낮은가"에 대한 답
1. **표현(파싱)의 문제가 아니었다.** 이중언어 문법을 충실히 복원해도(focal 120/120, directive 52/52) 미관측 enum 상태로의 gate 외삽은 0.58에 그친다. 즉 **병목은 한국어 매칭 방식이 아니라 120개 라벨이 담은 정보량**이다.
2. dev-only 규칙 유도로는 스크리닝의 절반을 차지하는 미관측 상태에서 gate ≥0.84를 지지할 수 없다(측정). champion이 이미 그보다 높은 일반화를 보이는 이유는 **여러 차례의 공개 제출 피드백으로 검증된 구조 가설들**이 누적돼 있기 때문이다.
3. 따라서 남은 상승 여지는 재설계가 아니라 **제출 1회당 하나의 미관측-상태 가설 검증**(예: 승인 stem 일반화가 +0.0039를 실증했던 방식)이다.

## 산출물
- `redesign/census.py` — dev 문장 인벤토리(템플릿 121종, 결정-절 17종 purity 1.0).
- `redesign/v2core.py` — 렉시콘·파서·enum 문법·프로시저·마이너·LOSO/LOEO 평가기(전부 stdlib, dev-only 입력).
- 기존 제출 코드(harness.py 등)는 무변경. 감사 게이트(redesign 포함) clean.

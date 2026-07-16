---
name: prd-intake
description: Use at the START of any new project, whenever spec/SPEC.yaml does not exist, or whenever the user provides/mentions a PRD, 기획서, 기획 문서, product spec, or asks to "start building" something that has no approved spec yet. Runs the full intake workflow - request the PRD, read it, interview the user on stack/tool choices, force concretization of every abstract sentence, and compile the approved spec/ artifacts. Implementation work must not begin before this completes.
---

# PRD Intake — 기획 문서를 승인된 SPEC으로 컴파일

Transplanted from a live-scored harness campaign: natural-language directives compiled to
typed concepts at purity 1.0 ONLY because uncompilable/uncertain sentences were routed to
"ask" instead of guessed. The same rule here: **a PRD sentence that doesn't compile to a
typed requirement is a QUESTION, never an implementation discretion.**

## Phase 0 — PRD 확보
`spec/SPEC.yaml`이 없으면 다른 어떤 작업보다 먼저 사용자에게 요청한다:
- "기획 문서(PRD)를 주세요 — 파일 경로 또는 본문 붙여넣기."
- 문서가 여러 개면 전부 받고 우선순위를 물어라. 문서가 아직 없다면 구두 요구사항을
  받아 이 워크플로우를 동일하게 적용한다.

## Phase 1 — 정독과 문장 인벤토리
PRD 전체를 읽고 **문장 단위**로 분해해 인벤토리를 만든다. 각 문장을 분류:
`requirement / constraint / context / non-goal`. 요구·제약 문장에는 임시 ID를 부여한다
(`PRD-<섹션>.<번호>`) — 이후 모든 산출물이 이 ID로 역추적된다.

## Phase 2 — 기술 스택·도구 인터뷰 (배치 질문, 1라운드 목표)
PRD가 이미 확정한 것은 다시 묻지 않는다. 나머지를 **카테고리별로 한 번에** 질문한다
(AskUserQuestion 사용 가능 시 활용, 각 항목에 추천안 + 근거 1줄 제시):
1. 런타임/프레임워크 (예: Next.js / Django / Spring …)
2. 데이터베이스·스토리지
3. 인증 방식 (자체 / OAuth 제공자 / 매니지드)
4. 배포 대상 (Vercel / AWS / 컨테이너 / 온프레미스)
5. PRD가 함의하는 외부 연동 — 결제·메일·실시간·검색 등 **PRD 문장에서 감지된 것만**
   (예: "구독 결제" 감지 → 결제 제공자 질문)
6. 테스트/CI 기대 수준
답변은 `spec/SPEC.yaml`의 `stack:` 섹션에 기록하고, 사용자가 "알아서"라고 답한 항목은
추천안을 적용하되 `assumption: true`로 표시한다(가역적 가정으로 관리).

## Phase 3 — 추상 문장 구체화 (핵심 단계)
요구·제약 문장 각각을 typed 요구로 컴파일 시도한다:
```
{actor, action, object, condition, acceptance_criterion}
```
**컴파일 실패 판정 기준** (하나라도 해당하면 UNCONFIRMED):
- 슬롯 누락: 누가/무엇을/어떤 대상에/언제가 특정되지 않음
- 모호 수식어 검출 — 아래 목록의 단어가 **측정 가능한 기준 없이** 사용됨:
  - 한국어: 빠르게, 쉽게, 편리하게, 간단히, 적절히, 유연하게, 안정적으로, 안전하게,
    직관적으로, 많은, 일부, 필요시, 가능하면, 최적화, 개선, 등/기타
  - 영어: fast, easy, user-friendly, intuitive, robust, scalable, seamless, secure,
    various, optimize, improve, etc.
- acceptance_criterion을 쓸 수 없음 (완료를 기계적/객관적으로 판정할 방법이 없음)
- 상충: 다른 요구와 모순되거나 stack 답변과 충돌

UNCONFIRMED 문장은 **절대 추측으로 메우지 않는다.** 대신:
1. `spec/OPEN-QUESTIONS.md`에 등재: 원문, PRD-ID, 무엇이 모호한지, **구체적 선택지 2~4개
   + 추천안** (열린 질문보다 선택지가 사용자 부담을 줄인다).
   예: "‘빠른 검색’(PRD-3.2) — 기준을 정해주세요: (a) p95 < 200ms [추천: 일반 SaaS 표준]
   (b) p95 < 1s (c) 타이핑 중 즉시(인크리멘털)"
2. 질문을 **주제별로 배치**해 1~2라운드 안에 해소한다 (한 문장씩 찔끔찔끔 묻지 않는다).
3. 사용자가 "나중에"라고 답하면: 가장 보수적/가역적 가정을 적용하고
   `assumption: true, revisit: <조건>`으로 기록한다.

## Phase 4 — 산출물 작성
```
spec/
├── SPEC.yaml            # stack + 승인된 typed 요구 목록
├── OPEN-QUESTIONS.md    # 미해결 질문 (비어있어야 승인 가능; 예외는 assumption 처리분)
└── ONTOLOGY.yaml        # (선택) 엔티티·관계·상태·불변식 시드 — docs/ontology-layers.md 스키마
```
`SPEC.yaml` 요구 항목 스키마:
```yaml
requirements:
  - id: R-001
    source: PRD-3.2                  # 역추적
    actor: Member
    action: search
    object: documents
    condition: "within own Org"
    acceptance: "p95 < 200ms on 10k docs; result set matches keyword AND filter"
    certainty: confirmed             # confirmed | assumption | deferred
    priority: must                   # must | should | could
```

## Phase 5 — 승인 게이트
SPEC 요약(요구 수, must/should 분포, 가정 목록, 스택)을 사용자에게 제시하고 **명시적
승인**을 받는다. 승인 후에야 다음 단계로:
- 게이트 결정(데이터 모델·인증 경계·API 계약·배포)을 walking-skeleton으로 실증
- 이후 기능 구현 (experiment-discipline 규율 적용)

## 금지 사항
- SPEC 승인 전 구현 시작
- UNCONFIRMED를 "일반적으로는 이렇게 하니까"로 자체 확정 (그건 assumption으로 명시
  표기된 경우에만 허용)
- PRD에 없는 기능의 임의 추가 (제안은 OPEN-QUESTIONS를 통해서만)

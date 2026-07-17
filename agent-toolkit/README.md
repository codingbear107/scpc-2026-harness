# Agent Toolkit v0.3 — 코딩 에이전트 운영 규율

SCPC 2026 하네스 캠페인(2026-07-08~16, 30+ 후보, 5회 실측 제출 사이클, 0.379→0.861)에서
얻은 방법을 재사용 형태로 정리한 툴킷입니다. **Claude Code 스킬 + 훅, 그리고 Codex용
운영 규칙(AGENTS.md)** 으로 구성됩니다 (Codex 쪽은 스킬 패키지가 아니라 규칙 문서입니다).

> v0.2: 외부 검토 반영 — checkpoint 안전 시맨틱(무단 전체 커밋 금지·태그 불변·원장 선기록),
> pre-commit의 staged-내용 검사, 훅의 구조화 JSON 출력($CLAUDE_PROJECT_DIR 사용),
> 시크릿 출력 마스킹, 스캔 범위 확장(JS/TS/JSON/YAML/Dockerfile/TF/SQL).
> v0.3: 오탐 완화 — 리터럴 원장은 기본적으로 **할당-문맥의 고엔트로피 문자열만** 검사
> (코드 내 URL은 정당한 경우가 흔해 STRICT_LITERAL_LEDGER opt-in으로 이동, 주석 줄 제외).
> 시크릿 DENYLIST는 .md까지 스캔. 훅·pre-commit의 인터프리터 자동 감지(py -3→python3→python)로
> Windows Store shim 문제를 코드로 해결.

## 구성

```
agent-toolkit/
├── README.md                    ← 이 파일 (사람용)
├── AGENTS.md                    ← Codex 등 에이전트용 운영 규칙 (프로젝트 루트에 복사/병합)
├── CLAUDE.md                    ← Claude Code 자동 로드 계약: spec/ 없으면 PRD 인테이크 강제
├── .claude/
│   ├── settings.json            ← Claude Code 훅 (Stop: 요약 보고 / PostToolUse: 발견 시 block+사유)
│   └── skills/
│       ├── prd-intake/SKILL.md              ← PRD 요청→스택 인터뷰→추상문장 구체화→SPEC 컴파일
│       ├── experiment-discipline/SKILL.md   ← 앵커·단일가설·킬기준·예산산술
│       ├── verify-agent-findings/SKILL.md   ← 에이전트 결론의 경험적 검증 프로토콜
│       └── metamorphic-testing/SKILL.md     ← 정답 없는 검증(불변성 테스트)
├── scripts/
│   ├── provenance_gate.py       ← 결정론 게이트 (--staged / --hook stop|posttool)
│   └── checkpoint.py            ← 게이트→원장→커밋→불변 태그 (dirty 시 명시 플래그 요구)
└── githooks/
    └── pre-commit               ← 게이트를 staged-내용 기준 커밋 차단으로
```

## 설치

```bash
cp -r agent-toolkit/.claude agent-toolkit/scripts <project>/
cp agent-toolkit/AGENTS.md agent-toolkit/CLAUDE.md <project>/   # 각 에이전트가 자동 로드
cp agent-toolkit/githooks/pre-commit <project>/.git/hooks/ && chmod +x <project>/.git/hooks/pre-commit
# 이후 scripts/provenance_gate.py 상단 CONFIG를 프로젝트에 맞게 조정
```

**강제층 vs 규범층** (정직한 구분): 하드 강제되는 것은 provenance 게이트(pre-commit
staged 차단)와 checkpoint 안전장치뿐입니다. experiment-discipline·verify-findings·
metamorphic 스킬과 prd-intake는 CLAUDE.md/AGENTS.md 자동 로드에 기대는 **규범(프롬프트)
층**으로, 에이전트의 준수를 기계적으로 검증하지 않습니다. 이 툴킷의 정체는 "완결된
자율 하네스"가 아니라 **반복 검증된 작업 규율의 재사용 형식화 + 소수의 결정론 게이트**입니다.

**시크릿 스캔의 한계**: DENYLIST 정규식은 1차 그물입니다 — base64 인코딩·분할된 값·
비정형 프로바이더 포맷은 놓칠 수 있습니다. 조직 차원 보안은 전용 도구(gitleaks 등)를
병행하세요.

## 각 구성요소의 근거 (등급 구분)

| 구성요소 | 근거 등급 | 내용 |
|---|---|---|
| experiment-discipline | **validated** (실측 제출) | 번들 변경 2회 회귀(원인 귀속 불가) vs 단일가설 프로브 2회 성공(+0.0039, +0.0063). 사전등록 킬 기준(LOEO≥0.84)이 재작성 후보의 제출 소비를 실제 차단 |
| verify-agent-findings | **validated** (실측) | 멀티에이전트 검토의 1순위 지목을 실측 1회로 기각(출력 변화 0) / 별도 패널의 버그 지적은 실측 확인 후 수정 |
| metamorphic-testing | **observed** | 델리미터-패러프레이즈 불변성 테스트가 대붕괴(0.379)의 **주요 원인 중 하나**(표면형 과적합)를 정답 없이 검출 — 게이트 연쇄·분포 이동 등 복합 원인 중 일부임 |
| provenance_gate | **observed** | LLM 멀티에이전트 감사가 잡은 검사 **항목들을** 결정론 게이트로 코드화해 이후 매 빌드 자동 검출 (동등성 비교 원자료는 없음 — 대체 주장 아님) |
| checkpoint | **observed** | 캠페인 전 후보를 태그·스냅샷·원장 기록, 회귀 2회를 태그 복원으로 롤백 |
| 온톨로지 매개 PRD→SPEC | **hypothesis** | SCPC의 닫힌-어휘·불변식 성공에서 유추한 설계 가설 — 미검증 |

## 새 프로젝트에서의 자동 흐름

툴킷이 설치된 폴더에서 에이전트 세션을 시작하면 (CLAUDE.md/AGENTS.md 자동 로드):
1. `spec/SPEC.yaml` 부재 감지 → **에이전트가 먼저 기획 문서(PRD)를 요청**
2. 정독 후 → **기술 스택·도구를 배치 질문** (PRD가 확정한 것은 안 물음, 항목별 추천안 제시)
3. 각 문장을 typed 요구 `{actor, action, object, condition, acceptance}`로 컴파일 시도 →
   **컴파일 실패(슬롯 누락·모호 수식어) = 추측 금지, 선택지 2~4개와 함께 구체화 질문**
4. 답변 반영 → `spec/SPEC.yaml`(+OPEN-QUESTIONS.md) 작성 → **사용자 승인 후에만** 구현 시작
5. 승인 후에도 게이트 결정(데이터모델·인증·API·배포)은 walking-skeleton 실증 후 기능 작업

## 훅 동작 (Claude Code)

- **PostToolUse**(Write|Edit): 발견 시 `{"decision":"block","reason":...}` JSON을 반환해
  **에이전트가 사유를 직접 읽고 수정**하게 합니다 (stdout echo가 아님).
- **Stop**: 발견 시 `systemMessage`로 사용자에게 요약 보고 (report-only).
- 하드 차단은 pre-commit(--staged)이 담당 — 커밋될 실제 내용을 검사합니다.

## 알려진 한계 / 다음 단계

- 이 툴킷은 **규율 층**입니다. "PRD→SPEC→GOALS→자율 루프" 전체 하네스가 목표라면,
  같은 구상을 이미 구현한 [Q00/ouroboros](https://github.com/Q00/ouroboros)
  (interview→seed→execute→evaluate→evolve, ontologist, immutable seed, ledger, replay,
  Codex/Claude 어댑터)를 **먼저 대표 PRD로 평가**하고, 부족분을 이 툴킷의 규율로 보완하는
  경로를 권장합니다. 자체 구현 시에는 `INTENT → 승인된 SPEC → GOALS → 실행 이벤트`의
  얇은 계약 계층부터.
- 자율 루프에는 작업트리 격리·권한 경계·예산·정지 조건·재실행 가능한 이벤트 로그가
  추가로 필요합니다 (이 툴킷 범위 밖).
- 온톨로지 스택(YAML→검색→그래프→실행→추론)의 계층별 채택 기준과 미래-호환
  스키마 요건은 [docs/ontology-layers.md](docs/ontology-layers.md) 참조 — 어떤 계층도
  "불필요"가 아니라 워크로드 임계 도달 시 붙이는 확장 장치입니다.

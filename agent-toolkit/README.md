# Agent Toolkit v0.2 — 코딩 에이전트 운영 규율

SCPC 2026 하네스 캠페인(2026-07-08~16, 30+ 후보, 5회 실측 제출 사이클, 0.379→0.861)에서
얻은 방법을 재사용 형태로 정리한 툴킷입니다. **Claude Code 스킬 + 훅, 그리고 Codex용
운영 규칙(AGENTS.md)** 으로 구성됩니다 (Codex 쪽은 스킬 패키지가 아니라 규칙 문서입니다).

> v0.2: 외부 검토 반영 — checkpoint 안전 시맨틱(무단 전체 커밋 금지·태그 불변·원장 선기록),
> pre-commit의 staged-내용 검사, 훅의 구조화 JSON 출력($CLAUDE_PROJECT_DIR 사용),
> 시크릿 출력 마스킹, 스캔 범위 확장(JS/TS/JSON/YAML/Dockerfile/TF/SQL).

## 구성

```
agent-toolkit/
├── README.md                    ← 이 파일 (사람용)
├── AGENTS.md                    ← Codex 등 에이전트용 운영 규칙 (프로젝트 루트에 복사/병합)
├── .claude/
│   ├── settings.json            ← Claude Code 훅 (Stop: 요약 보고 / PostToolUse: 발견 시 block+사유)
│   └── skills/
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
cp agent-toolkit/AGENTS.md <project>/            # Claude Code만 쓰면 CLAUDE.md에 병합
cp agent-toolkit/githooks/pre-commit <project>/.git/hooks/ && chmod +x <project>/.git/hooks/pre-commit
# 이후 scripts/provenance_gate.py 상단 CONFIG를 프로젝트에 맞게 조정
```

**Windows 주의**: `python`이 Microsoft Store shim(exit 9009)으로 잡히는 환경에서는
settings.json·pre-commit의 `python`을 `py -3` 또는 인터프리터 절대경로로 바꿔야 합니다.

## 각 구성요소의 근거 (등급 구분)

| 구성요소 | 근거 등급 | 내용 |
|---|---|---|
| experiment-discipline | **validated** (실측 제출) | 번들 변경 2회 회귀(원인 귀속 불가) vs 단일가설 프로브 2회 성공(+0.0039, +0.0063). 사전등록 킬 기준(LOEO≥0.84)이 재작성 후보의 제출 소비를 실제 차단 |
| verify-agent-findings | **validated** (실측) | 멀티에이전트 검토의 1순위 지목을 실측 1회로 기각(출력 변화 0) / 별도 패널의 버그 지적은 실측 확인 후 수정 |
| metamorphic-testing | **observed** | 델리미터-패러프레이즈 불변성 테스트가 대붕괴(0.379)의 **주요 원인 중 하나**(표면형 과적합)를 정답 없이 검출 — 게이트 연쇄·분포 이동 등 복합 원인 중 일부임 |
| provenance_gate | **observed** | LLM 멀티에이전트 감사가 잡은 검사 **항목들을** 결정론 게이트로 코드화해 이후 매 빌드 자동 검출 (동등성 비교 원자료는 없음 — 대체 주장 아님) |
| checkpoint | **observed** | 캠페인 전 후보를 태그·스냅샷·원장 기록, 회귀 2회를 태그 복원으로 롤백 |
| 온톨로지 매개 PRD→SPEC | **hypothesis** | SCPC의 닫힌-어휘·불변식 성공에서 유추한 설계 가설 — 미검증 |

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

# Agent Toolkit — 검증된 코딩 에이전트 운영 규율

SCPC 2026 하네스 캠페인(0.379 → 0.861, 30+ 후보, 5회 실측 제출 사이클)에서 **실제로 효과가 검증된
방법**만 추려 만든 재사용 툴킷입니다. Claude Code와 Codex(및 AGENTS.md를 읽는 모든 에이전트)에서
그대로 사용할 수 있습니다.

## 구성

```
agent-toolkit/
├── README.md                    ← 이 파일 (사람용)
├── AGENTS.md                    ← Codex 등 에이전트용 운영 규칙 (프로젝트 루트에 복사/병합)
├── .claude/
│   ├── settings.json            ← Claude Code 훅 템플릿 (Stop 훅: 품질 게이트 자동 실행)
│   └── skills/
│       ├── experiment-discipline/SKILL.md   ← 단일가설·킬기준·예산산술·앵커 규율
│       ├── verify-agent-findings/SKILL.md   ← 에이전트 결론의 경험적 검증 프로토콜
│       └── metamorphic-testing/SKILL.md     ← 정답 없는 검증(불변성 테스트)
├── scripts/
│   ├── provenance_gate.py       ← 결정론적 품질/출처 게이트 (pre-commit·훅·CI 겸용)
│   └── checkpoint.py            ← 실험 체크포인트: 게이트→스냅샷→태그→원장 기록
└── githooks/
    └── pre-commit               ← provenance_gate를 커밋 차단 게이트로
```

## 설치 (새 프로젝트에)

```bash
# 1. 툴킷 복사
cp -r agent-toolkit/.claude  <project>/
cp -r agent-toolkit/scripts  <project>/scripts
cp    agent-toolkit/AGENTS.md <project>/          # Codex용. Claude Code만 쓰면 CLAUDE.md에 병합

# 2. git 훅 연결 (커밋 차단 게이트)
cp agent-toolkit/githooks/pre-commit <project>/.git/hooks/pre-commit
chmod +x <project>/.git/hooks/pre-commit

# 3. 프로젝트에 맞게 조정
#    scripts/provenance_gate.py 상단의 CONFIG(denylist·allowlist·검사 대상)를 프로젝트에 맞춤
```

## 각 구성요소의 출처 (캠페인 실증)

| 구성요소 | 검증된 사례 |
|---|---|
| experiment-discipline | 번들 변경 2회 회귀(원인 귀속 불가) vs 단일가설 프로브 2회 성공(+0.0039, +0.0063). 사전등록 킬 기준(LOEO≥0.84)이 무가치한 재작성의 제출 낭비를 실제로 차단 |
| verify-agent-findings | 4-에이전트 워크플로우의 "최대 레버" 지목이 실측 1회로 완전 기각(영향 0). 5-엔지니어 패널의 버그 지적은 실측 확인 후 수용 → 진짜 버그 수정 |
| metamorphic-testing | 델리미터-패러프레이즈 불변성 테스트(MR4)가 점수 붕괴(0.38)의 원인을 정답 없이 규명 |
| provenance_gate | LLM 멀티에이전트 감사(19 에이전트, 7분)가 잡던 검사를 결정론적 게이트로 코드화 — 이후 매 빌드 0초에 동일 검출 |
| checkpoint | 30+ 후보 전부 태그·스냅샷·원장 기록 → 어느 시점이든 1커맨드 복원, 회귀 2회를 무손실 롤백 |

## Claude Code에서

- 스킬은 `.claude/skills/`에 있으면 자동 인식됩니다. 위험한 변경·최적화·다중 에이전트 검토 상황에서
  해당 스킬이 트리거됩니다.
- `.claude/settings.json`의 Stop 훅이 매 턴 종료 시 게이트를 report-only로 실행합니다
  (차단은 pre-commit이 담당 — 이중 게이트).

## Codex에서

- `AGENTS.md`가 저장소 루트에 있으면 자동으로 읽습니다. 스킬 내용의 핵심 규칙이 요약돼 있고,
  `scripts/`의 두 도구는 에이전트가 직접 호출하도록 지시되어 있습니다.

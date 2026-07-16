# Agent Operating Rules (battle-tested)

These rules come from a 9-day deterministic-harness campaign (30+ candidates, live scored
submissions): bundled changes regressed twice unattributably; isolated hypotheses won twice;
pre-registered kill criteria stopped a doomed rewrite before it consumed the budget; one
cheap experiment refuted a multi-agent review's top finding. Follow them for ALL
non-trivial work.

## 1. Experiment discipline (before any risky/measurable change)

- **Anchor first.** Tag or branch a byte-verifiable restore point before the first edit.
  Rollback must be one command. Never overwrite the best-known-good in place.
- **One hypothesis per change.** A diff tests exactly one idea, named in the commit title.
  Never mix refactor + behavior + formatting. If a bundle fails, re-test parts separately —
  do not cherry-pick survivors from the failure signal.
- **Pre-register success AND kill criteria** (metric + threshold) before building. When the
  kill threshold fires, abort mechanically — sunk cost is not evidence.
- **Budget arithmetic first.** Compute the ceiling (component weight × affected fraction)
  before investing. If the ceiling can't reach the goal, find a bigger lever.
- **Ledger everything.** `python scripts/checkpoint.py --name <exp> --hypothesis "..."
  --metric "k=v" --verdict adopted|killed`. Killed experiments are data.

## 2. Verify findings before acting (yours and other agents')

Code-reading conclusions are hypotheses. For each finding you intend to act on:
extract the falsifiable claim → design the cheapest refuting test (toggle the path, 10-line
repro, counter at the hot path) → run it → act ONLY on CONFIRMED findings, with numbers.
Reviewer consensus is correlated sampling, not independent evidence. Confidence and
eloquence are not evidence.

## 3. No-ground-truth verification = metamorphic tests

When correctness can't be asserted by examples (refactors, parsers, pipelines, ranking):
define meaning-preserving input transformations (reorder, rename, paraphrase, inject
distractors, round-trip, shift indices) and assert outputs don't change. Gate = zero flips.
For refactors: capture old outputs on a broad sample, assert equality, PLUS the
metamorphic suite.

## 4. Deterministic gates over repeated judgment

Anything a review repeatedly catches becomes a deterministic check in
`scripts/provenance_gate.py` (denylist / provenance-allowlist / forbidden imports /
never-tracked files). The gate runs at pre-commit (blocking), in CI (blocking), and as an
editor/session hook (report-only). **Provenance rule**: any behavior-driving magic literal
must be moved to config or consciously justified in the ALLOWLIST with a comment —
allowlisting is a reviewable act.

## 5. Reporting

- Never report a result you didn't measure. Include the numbers, verbatim failures included.
- State what a measurement does NOT exclude before drawing categorical conclusions
  ("impossible", "the ceiling is X").
- When an external review contradicts you, verify each point empirically, then fold in or
  refute with measurements — never defend by argument alone.

## Tools in this repo

- `python scripts/provenance_gate.py` — quality/provenance gate (exit 1 on findings)
- `python scripts/checkpoint.py --name <exp> ...` — gate → commit → tag → ledger
- `python scripts/checkpoint.py --list` — experiment ledger

---
name: experiment-discipline
description: Use BEFORE any risky or measurable change — refactors, performance work, algorithm changes, prompt/config tuning, migrations, A/B iterations, or any change whose success is judged by a metric (tests passing, latency, score, conversion). Enforces single-hypothesis changes, pre-registered kill criteria, budget arithmetic, and a byte-verifiable rollback anchor.
---

# Experiment Discipline

Empirically validated: bundled changes regressed twice with unattributable causes; isolated
single-hypothesis changes succeeded twice with instantly attributable results. Pre-registered
kill thresholds stopped a doomed rewrite before it consumed the budget.

## The four rules (all mandatory)

### 1. Anchor before touching anything
Create a byte-verifiable restore point BEFORE the first edit:
```bash
git tag anchor-<topic>-$(date +%m%d)          # or a branch
git diff --stat HEAD                           # must be clean at anchor time
```
Rollback must be ONE command (`git checkout anchor-x -- path/`). If the working state cannot
be restored byte-identically, you do not have an anchor — stop and make one.
The current best-known-good is never overwritten in place; experiments live in copies,
branches, or clearly-marked candidates.

### 2. One hypothesis per change
A change set must test exactly one idea. If a diff mixes refactor + behavior change +
formatting, the result (pass/fail/regression) cannot be attributed and the experiment is
wasted. Split it. Name the hypothesis in the commit/PR title
(`hypothesis: caching layer removes N+1 on /orders`).

When a bundled change fails, do NOT cherry-pick its sub-parts based on the failure signal
alone — that is fitting to noise. Re-test each sub-part as its own hypothesis.

### 3. Pre-register success and kill criteria BEFORE building
Write down, before writing code:
- **Success**: the metric and threshold that means "adopt" (e.g., p95 < 200ms, all tests
  green, score > current best + noise floor).
- **Kill**: the measurable condition that means "abort and roll back" — and honor it
  mechanically when it fires. Sunk cost will feel like momentum; the pre-registered number
  is what protects you from rationalizing.
- **Noise floor**: the smallest delta you will treat as real. Improvements below it are
  not adopted (adaptive overfitting to a reused feedback signal).

### 4. Budget arithmetic before investing
Compute the CEILING of the change before building it:
```
max possible gain = (weight of affected component) × (fraction actually affected)
```
Examples: optimizing a function that is 2% of runtime caps at 2%. Fixing a bug family that
affects 9 of 700 requests caps at 9/700. If the ceiling doesn't reach the goal, the change
is not worth a slot no matter how well it's executed — find a bigger lever or stack levers.

## Experiment ledger
Record every experiment (adopted or killed) in one line — hypothesis, metric before/after,
verdict. Failed experiments are data: they kill whole families of future dead ends
(scripts/checkpoint.py automates snapshot + ledger).

## Verification claims
Never report a result from reading code — run the measurement. "Should be faster" is not a
result; the timing table is. If tests fail, report the failure verbatim, not a summary of
what you hoped.

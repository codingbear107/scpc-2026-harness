---
name: verify-agent-findings
description: Use whenever acting on conclusions produced by an agent, subagent, multi-agent workflow, code review bot, or your own code-reading — bug reports, "root cause" claims, optimization suggestions, architecture findings. Requires the cheapest empirical test to CONFIRM or REFUTE each finding before any code change is made based on it.
---

# Verify Agent Findings Before Acting

Empirically validated both ways: a 4-agent review workflow's single highest-ranked finding
("this mapping bug drives 200+ failures") was REFUTED by one 30-second experiment (zero
output change — the mapped value was dead). A 5-engineer panel's bug report was CONFIRMED
by measurement and fixed a real defect. Code-reading conclusions — including your own —
are hypotheses, not facts.

## Protocol

For EACH finding you intend to act on:

1. **Extract the falsifiable claim.** "X causes Y" must predict something observable:
   "if I change X, output Z changes / test T flips / metric M moves."
2. **Design the cheapest test that could refute it.** Usually one of:
   - Toggle the suspect code path (monkeypatch, feature flag, one-line edit on a scratch
     copy) and diff the observable output before/after.
   - Write a 10-line reproduction script.
   - Add a counter/log at the claimed hot path and run the existing suite.
3. **Run it. Record CONFIRMED / REFUTED / PARTIAL with the measured numbers.**
4. **Act only on CONFIRMED findings.** REFUTED findings are reported back (they often
   reveal the reviewer's wrong mental model — itself useful).

## Rules of thumb

- The more confident and elaborate the agent's explanation, the MORE it needs the test —
  fluency is not evidence.
- Rank findings by (claimed impact × cost to verify) and verify top-down; don't fix
  bottom-up just because small items are easy.
- When multiple reviewers agree, that is correlated sampling, not independent evidence —
  they read the same code with similar priors. Still test.
- A verification that requires the full fix to be built first is not a verification.
  Find the observable that moves without building the fix.
- Never bundle "fix for confirmed finding" with "fixes for unverified ones" in one change
  (see experiment-discipline: one hypothesis per change).

## Report format

```
finding: <one line>
test:    <what was toggled/run>
result:  CONFIRMED | REFUTED — <measured numbers>
action:  <fix applied / dropped / needs deeper test>
```

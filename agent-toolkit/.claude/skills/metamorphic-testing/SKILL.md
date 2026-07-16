---
name: metamorphic-testing
description: Use when correctness must be verified WITHOUT ground truth — refactors that must preserve behavior, parsers, data pipelines, search/ranking, LLM-integrated features, migrations, serialization. Builds invariance tests (output must not change under meaning-preserving input transformations) instead of example-based assertions.
---

# Metamorphic Testing (no-ground-truth verification)

Empirically validated: an invariance suite (delimiter/paraphrase transformations) explained
a production-scale failure that no example-based test caught — the system was matching
surface forms, not meaning, and collapsed on inputs phrased differently. The invariance
test found this WITHOUT knowing any correct answer.

## Core idea

You often can't say what the correct output IS, but you can say what must NOT change it.
Define meaning-preserving transformations T of the input; assert `f(T(x)) == f(x)`
(or a known relation). Zero labels required, and the suite runs on ANY input — including
production samples.

## Standard transformation catalog (pick what applies)

| Class | Transformations | Catches |
|---|---|---|
| Ordering | shuffle array/dict/query-param order where semantics say order is irrelevant | hidden positional dependence |
| Naming | rename identifiers, ids, channel/user names consistently | hardcoded-name coupling |
| Surface form | paraphrase, synonyms, whitespace, delimiter style (`a, b` vs `a / b`), casing | surface-string matching that should be semantic |
| Injection | add irrelevant/distractor records, fields, log lines | over-broad matching, lack of scoping |
| Translation | shift timestamps/indices by a constant | absolute-position dependence |
| Round-trip | serialize→deserialize, format→parse | lossy codecs, asymmetric schemas |
| Monotonicity | a strictly more restrictive input must never yield a more permissive output | inverted or missing guard logic |
| Deletion | remove known-boilerplate/no-op elements | decisions leaking from non-decision content |

## How to build the suite (30-90 min)

1. List the invariances your spec ALREADY implies ("array order is meaningless",
   "renaming a tenant must not change routing"). Each is one test.
2. Implement each T as a pure function on the input fixture; run the real system on
   x and T(x); diff full outputs (not just status codes).
3. **Gate = zero flips.** A single flip is a real bug or a real (undocumented) semantic —
   either way, you learned something a green example test would have hidden.
4. Add the suite to CI next to unit tests; it is cheap and label-free.

## For refactors specifically

Before refactoring: capture `f_old(x)` for a broad input sample (including weird
production-ish inputs). After: assert `f_new(x) == f_old(x)` on all of them, AND run the
metamorphic suite on f_new. Equivalence on samples + invariance on transformations is far
stronger than either alone.

## Anti-patterns

- Testing only the transformations that pass (pick T adversarially — what WOULD break a
  lazy implementation?).
- Treating a flip as "flaky" and rerunning until green.
- Building T with the same helper functions the system under test uses (shared bugs cancel out).

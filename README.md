# SCPC 2026 AI Agent Harness

A deterministic, rule-based harness that reads a task JSON (prompt, `visible_history`,
`device_state.objects/records`, `personal_memory`) and produces the structured answer
(`focal_id`, `target`, `control`, `content_scope`, `policy`, `plan_events`,
`user_response`, `audit_tags`).

No external LLM/API is used. `meta.uses_external_api` is `false` and
`meta.fixed_slm_policy` is `local_fixed_slm_only`; the final fields are produced by the
harness logic (the fixed SLM facade is not an answer oracle).

## Design principles

All rules are derived from the labeled development set (`data/dev_answers.json`) plus
general domain/language knowledge, and are written against **structure and meaning**, not
task-specific surface strings:

- **Focal** — a delimiter/phrasing-agnostic semantic parser reads candidate-reference
  lists by their meaning (an ordinal into the listed order, an approval marker on one
  code, or a single designated reference) rather than fixed phrasings.
- **Control** — the request's trailing corrective directive is classified into four
  intents (stop / confirm / keep-local / redact) using general Korean concept vocabulary;
  when no directive is present, the decision follows the structured record signals.
- **Target** — follows the decision provenance: a "keep local" decision or a memory-write
  writes to internal memory; a directive-driven confirm/stop responds to the user; a
  record-driven confirm/stop keeps the channel the operation was headed to. When no
  destination is stated on the turn, it is taken from the focal object's own
  recipient/channel attributes. Channels are judged structurally (`is_external_channel`).
- **Content scope** — contextual-integrity data minimization: a fixed minimal exclusion
  set per mode.
- **Policy** — flags are emitted only on cited structural evidence.

Person profiles (channels, avoid-preferences) are read from the persistent-memory store
by `memory_key`/`person`; there is no hardcoded name→value table. Route/boundary values
are matched by structural stems, so unseen values generalize.

## Robustness

The intent classifier is verified **synonym-robust**: paraphrasing the directive verbs in
the dev set (e.g. 멈춰야→중단해야, 먼저 확인→먼저 물어봐야) leaves `control` unchanged
(0 flips). The focal parser is invariant to delimiter/ordinal paraphrase (0 focal flips).
Cross-field invariants hold on all outputs (`amend`⇒`redacted`, `hold`⇒`none`,
`ask`⇒confirmations, `violations`⇔`hold`).

## Files

- `harness.py` — the harness (`FinalHarness`), scorer-agnostic runner, CSV I/O, validation.
- `run_dev.py` — local dev scoring and per-axis / failure reports.
- `make_submission.py` — generate `submission.csv` (single-cell JSON payload) with a
  round-trip check.

## Run

```bash
python run_dev.py                 # score on the 120 dev tasks
python make_submission.py         # write submission.csv for the screening tasks
```

## Reproducing `submission.csv`

- **Python**: 3.10+ (developed and tested on CPython 3.14). No third-party packages —
  standard library only. No external LLM/API/network calls, no pretrained artifacts.
- **File placement**: put the provided competition data under `data/` next to the code:
  - `data/screening_tasks.jsonl` (evaluation inputs)
  - `data/dev_tasks.jsonl`, `data/dev_answers.json` (labeled dev set, used only by `run_dev.py`)
- **Regenerate**: `python make_submission.py` writes `submission.csv` (a single-cell JSON
  payload in a `submission` column, 700 answers) with a built-in round-trip check.
- **Determinism**: the harness is fully deterministic — no randomness, sampling, or
  time/seed dependence. All set-derived output fields are sorted, so `python
  make_submission.py` reproduces the identical `submission.csv` byte-for-byte on any
  machine and any `PYTHONHASHSEED`. (`meta.seed` is a fixed constant recorded for
  provenance; it is not used to drive any sampling.)
- The same `FinalHarness` runs unchanged on unseen tasks: it reads each task's public
  `prompt` / `device_state` / `records` / `visible_history` / `personal_memory` and
  produces every answer field by the general rules above.

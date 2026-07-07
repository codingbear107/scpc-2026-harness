from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from harness import FinalHarness, load_json, load_jsonl, run_harness, validate_payload


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

WEIGHTS = {
    "focal": 0.18,
    "target": 0.12,
    "control": 0.18,
    "content_scope": 0.17,
    "policy": 0.13,
    "plan": 0.18,
    "semantic_response": 0.04,
    "counterfactual": 0.0,
}

PLAN_ARG_KEYS = {
    "purpose",
    "reason",
    "scope",
    "state",
    "remove",
    "mode",
    "status",
    "duration",
    "person",
    "check",
    "condition",
    "lesson",
    "time",
    "rule",
    "method",
    "date",
    "principle",
}

PLAN_ARG_VALUE_ALIASES = {
    "inspect": "inspect_context",
    "inspect_fields": "inspect_context",
    "inspect_task_context": "inspect_context",
    "internal_binding_confirmed": "route_verified",
    "local_update_only": "local_update",
    "latest_local_update_override": "local_update",
    "raw_quote_location_numeric_value": "sensitive_fields",
    "raw_sensitive_forbidden": "sensitive_fields",
    "raw_quote_forbidden": "raw_quote_blocked",
    "doctor_note_forbidden": "sensitive_fields",
    "summary_only_allowed": "summary_share",
    "resolved_target_precedence": "latest_target_precedence",
    "recipient_conflicts_with_latest_target": "target_conflict",
    "target_changed_after_turn": "target_changed",
    "prior_success_invalidation": "prior_success_invalidated",
    "strict_policy_block_ambiguous": "strict_policy_block",
    "stored_channel_or_visible_recipient": "target_ambiguity",
    "temporary_or_always": "duration_ambiguous",
    "stored_gift_payment_requires_confirmation": "payment_confirmation_required",
    "minor_location_protected": "minor_location_protection",
    "latest_tone_conflicts_with_stored_preference": "memory_conflict",
}

PUBLIC_PLAN_ARG_VALUES = {
    "ambiguous_focal",
    "amount_changed",
    "appointment_time",
    "calendar_conflict",
    "clarification_required",
    "clarify_precondition",
    "compare_candidates",
    "conflict_check",
    "consent_check",
    "consent_revoked",
    "dependent_safety",
    "duration_ambiguous",
    "duration_check",
    "duration_limit",
    "enabled",
    "external_redacted_summary",
    "fast_path_invalidation",
    "guardrail_ladder",
    "health_external_share_blocked",
    "health_policy",
    "health_scope",
    "health_status_only",
    "impersonation_suspected",
    "inspect_context",
    "invalidated_precondition",
    "latest_target_precedence",
    "local_status_only",
    "local_update",
    "location",
    "medication_confirmation",
    "medication_time",
    "memory_channel",
    "memory_conflict",
    "memory_fast_path",
    "memory_preference",
    "memory_read",
    "memory_write",
    "minimal_disclosure",
    "minor_location_protection",
    "named_recipient",
    "none",
    "numeric_value",
    "numeric_value_blocked",
    "one_time",
    "payment_confirmation_required",
    "payment_details",
    "payment_memory",
    "payment_method_check",
    "payment_policy",
    "payment_security_check",
    "phishing",
    "policy_ok",
    "precondition_changed",
    "precondition_invalidated",
    "prior_failure_lesson",
    "prior_result_reuse",
    "prior_success_invalidated",
    "privacy_guard",
    "privacy_rule",
    "privacy_rule_violation",
    "raw",
    "raw_quote",
    "raw_quote_blocked",
    "recurrence_ambiguity",
    "redacted",
    "redacted_external",
    "route_resolution_required",
    "route_verified",
    "routine_scope",
    "safe_routine",
    "same_place_scope_check",
    "schedule_context",
    "scheduled_date",
    "scheduled_time",
    "scope_check",
    "security_alert",
    "security_check",
    "sensitive_fields",
    "sensitive_identifier",
    "stale_target",
    "standing_constraint",
    "status_only",
    "strict_policy_block",
    "strict_share_policy",
    "summary",
    "summary_share",
    "target_ambiguity",
    "target_changed",
    "target_conflict",
    "target_scope_check",
    "temporary",
    "temporary_allowed",
    "temporary_override",
    "trusted_subscription",
    "update",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).strip()


def _set(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        value = [value]
    return {_text(v).lower() for v in value if _text(v)}


def _f1(pred: set[str], reference: set[str]) -> float:
    if not pred and not reference:
        return 1.0
    if not pred or not reference:
        return 0.0
    hit = len(pred & reference)
    if hit == 0:
        return 0.0
    precision = hit / len(pred)
    recall = hit / len(reference)
    return 2 * precision * recall / (precision + recall)


def _norm_plan_arg(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _canon_plan_arg_value(value: Any) -> str:
    token = _norm_plan_arg(value)
    if re.fullmatch(r"\d{2}_\d{2}", token):
        try:
            first = int(token.split("_", 1)[0])
        except ValueError:
            first = 99
        return "scheduled_date" if first <= 12 else "scheduled_time"
    if token in PLAN_ARG_VALUE_ALIASES:
        return PLAN_ARG_VALUE_ALIASES[token]
    return token if token in PUBLIC_PLAN_ARG_VALUES else ""


def _plan_arg_sets(event: dict[str, Any]) -> tuple[set[str], set[str]]:
    args = event.get("args")
    pairs: set[str] = set()
    values: set[str] = set()
    if not isinstance(args, dict):
        return pairs, values
    for key, value in args.items():
        k = _norm_plan_arg(key)
        if k not in PLAN_ARG_KEYS:
            continue
        v = _canon_plan_arg_value(value)
        if not v:
            continue
        pairs.add(k + ":" + v)
        values.add(v)
    return pairs, values


def _plan_arg_similarity(pred: dict[str, Any], reference: dict[str, Any]) -> float:
    pred_pairs, pred_values = _plan_arg_sets(pred)
    reference_pairs, reference_values = _plan_arg_sets(reference)
    if not reference_values:
        return 1.0
    value_score = _f1(pred_values, reference_values)
    pair_score = _f1(pred_pairs, reference_pairs) if reference_pairs else value_score
    return round(0.65 * value_score + 0.35 * pair_score, 4)


def _scope_score(pred: dict[str, Any], reference: dict[str, Any]) -> float:
    pred = pred if isinstance(pred, dict) else {}
    reference = reference if isinstance(reference, dict) else {}
    mode = 1.0 if _text(pred.get("mode")) == _text(reference.get("mode")) else 0.0
    allowed = _f1(_set(pred.get("allowed_fields")), _set(reference.get("allowed_fields")))
    excluded = _f1(_set(pred.get("excluded_fields")), _set(reference.get("excluded_fields")))
    confirm = 1.0 if bool(pred.get("requires_user_confirmation")) == bool(reference.get("requires_user_confirmation")) else 0.0
    return 0.40 * mode + 0.25 * allowed + 0.25 * excluded + 0.10 * confirm


def _policy_score(pred: dict[str, Any], reference: dict[str, Any]) -> float:
    pred = pred if isinstance(pred, dict) else {}
    reference = reference if isinstance(reference, dict) else {}
    flags = _f1(_set(pred.get("risk_flags")), _set(reference.get("risk_flags")))
    violations = _f1(_set(pred.get("violations")), _set(reference.get("violations")))
    confirm = 1.0 if bool(pred.get("requires_confirmation")) == bool(reference.get("requires_confirmation")) else 0.0
    return 0.45 * flags + 0.35 * violations + 0.20 * confirm


def _event_similarity(pred: Any, expected: Any) -> float:
    if not isinstance(pred, dict) or not isinstance(expected, dict):
        return 0.0
    if _text(pred.get("verb")) != _text(expected.get("verb")):
        return 0.0
    score = 0.40
    if _text(pred.get("target")) == _text(expected.get("target")):
        score += 0.30
    score += 0.30 * _plan_arg_similarity(pred, expected)
    return min(score, 1.0)


def _plan_score(pred_events: Any, expected_events: Any) -> float:
    pred_events = pred_events if isinstance(pred_events, list) else []
    expected_events = expected_events if isinstance(expected_events, list) else []
    if not expected_events:
        return 1.0 if not pred_events else 0.5

    used = set()
    unordered_total = 0.0
    for expected in expected_events:
        best = 0.0
        best_idx = -1
        for idx, pred in enumerate(pred_events):
            if idx in used:
                continue
            sim = _event_similarity(pred, expected)
            if sim > best:
                best = sim
                best_idx = idx
        if best_idx >= 0:
            used.add(best_idx)
        unordered_total += best
    unordered_recall = unordered_total / len(expected_events)

    ordered_total = 0.0
    cursor = 0
    for expected in expected_events:
        best = 0.0
        best_idx = -1
        for idx in range(cursor, len(pred_events)):
            sim = _event_similarity(pred_events[idx], expected)
            if sim > best:
                best = sim
                best_idx = idx
        if best_idx >= 0:
            cursor = best_idx + 1
        ordered_total += best
    ordered_recall = ordered_total / len(expected_events)

    recall = 0.50 * unordered_recall + 0.50 * ordered_recall
    extra = max(0, len(pred_events) - len(used))
    return max(0.0, recall - min(0.30, 0.06 * extra))


def score_dev_submission(payload: dict[str, Any], reference_payload: dict[str, Any]) -> dict[str, Any]:
    reference_answers = reference_payload.get("answers", {})
    validate_payload(payload)
    answers = payload.get("answers", {}) if isinstance(payload.get("answers"), dict) else {}
    missing = sorted(set(reference_answers) - set(answers))
    if missing:
        raise ValueError(f"missing dev reference answers: {missing[:5]} ... total={len(missing)}")

    rows = []
    for task_id, reference in reference_answers.items():
        pred = answers.get(task_id, {})
        focal = 1.0 if _text(pred.get("focal_id")) == _text(reference.get("focal_id")) else 0.0
        target = focal * (1.0 if _text(pred.get("target")) == _text(reference.get("target")) else 0.0)
        control = focal * (1.0 if _text(pred.get("control")) == _text(reference.get("control")) else 0.0)
        dependent = target * control
        scope_raw = _scope_score(pred.get("content_scope"), reference.get("content_scope"))
        policy_raw = _policy_score(pred.get("policy"), reference.get("policy"))
        plan_raw = _plan_score(pred.get("plan_events"), reference.get("expected_events"))
        axes = {
            "focal": focal,
            "target": target,
            "control": control,
            "content_scope": dependent * scope_raw,
            "policy": dependent * policy_raw,
            "plan": dependent * plan_raw,
            "semantic_response": 0.0,
            "counterfactual": 0.0,
        }
        score = sum(axes[k] * WEIGHTS[k] for k in WEIGHTS)
        rows.append(
            {
                "task_id": task_id,
                "score": score,
                "axes": axes,
                "raw": {"scope": scope_raw, "policy": policy_raw, "plan": plan_raw},
            }
        )
    overall = sum(r["score"] for r in rows) / len(rows) if rows else 0.0
    axes_avg = {k: sum(r["axes"][k] for r in rows) / len(rows) if rows else 0.0 for k in WEIGHTS}
    return {
        "overall": round(overall, 4),
        "n": len(rows),
        "axes": {k: round(v, 4) for k, v in axes_avg.items()},
        "rows": rows,
    }


def record_set(task: dict[str, Any]) -> str:
    records = task.get("device_state", {}).get("records", []) or []
    return "|".join(sorted({str(r.get("type")) for r in records}))


def plan_pattern(answer: dict[str, Any], reference: bool = False) -> str:
    key = "expected_events" if reference else "plan_events"
    return ">".join(str(e.get("verb")) for e in answer.get(key, []) or [])


def build_failure_report(
    tasks: list[dict[str, Any]],
    payload: dict[str, Any],
    reference: dict[str, Any],
    traces: dict[str, dict[str, Any]],
    scored_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    task_by_id = {str(t["id"]): t for t in tasks}
    pred_answers = payload["answers"]
    ref_answers = reference["answers"]
    row_by_id = {row["task_id"]: row for row in scored_rows}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    record_stats: dict[str, Counter[str]] = defaultdict(Counter)
    resolver_stats: Counter[str] = Counter()
    plan_stats: Counter[str] = Counter()

    for task_id, ref in ref_answers.items():
        pred = pred_answers.get(task_id, {})
        task = task_by_id[task_id]
        trace = traces.get(task_id, {})
        resolver_stats[str(trace.get("resolver_source") or "unknown")] += 1
        record_key = record_set(task)
        row = row_by_id[task_id]

        failure_types = []
        if pred.get("focal_id") != ref.get("focal_id"):
            failure_types.append("focal_miss")
        if pred.get("target") != ref.get("target"):
            failure_types.append("target_miss")
        if pred.get("control") != ref.get("control"):
            failure_types.append("control_miss")
        if row["raw"]["scope"] < 1.0:
            failure_types.append("scope_miss")
        if row["raw"]["policy"] < 1.0:
            failure_types.append("policy_miss")
        if row["raw"]["plan"] < 1.0:
            failure_types.append("plan_miss")

        for failure_type in failure_types:
            record_stats[record_key][failure_type] += 1
        if plan_pattern(pred) != plan_pattern(ref, reference=True):
            plan_stats[f"{plan_pattern(pred)} -> {plan_pattern(ref, reference=True)}"] += 1

        if failure_types:
            item = {
                "task_id": task_id,
                "score": round(row["score"], 4),
                "failures": failure_types,
                "record_set": record_key,
                "resolver_source": trace.get("resolver_source"),
                "decision_class": trace.get("decision_class"),
                "pred": {
                    "focal_id": pred.get("focal_id"),
                    "target": pred.get("target"),
                    "control": pred.get("control"),
                    "mode": (pred.get("content_scope") or {}).get("mode"),
                    "plan": plan_pattern(pred),
                },
                "ref": {
                    "focal_id": ref.get("focal_id"),
                    "target": ref.get("target"),
                    "control": ref.get("control"),
                    "mode": (ref.get("content_scope") or {}).get("mode"),
                    "plan": plan_pattern(ref, reference=True),
                },
                "trace": trace,
                "prompt": task.get("prompt"),
            }
            for failure_type in failure_types:
                buckets[failure_type].append(item)

    return {
        "failure_counts": {key: len(value) for key, value in sorted(buckets.items())},
        "resolver_sources": dict(resolver_stats.most_common()),
        "plan_mismatches": dict(plan_stats.most_common(30)),
        "record_set_failures": {
            key: dict(counter)
            for key, counter in sorted(
                record_stats.items(), key=lambda kv: sum(kv[1].values()), reverse=True
            )[:30]
        },
        "examples": {key: value[:20] for key, value in buckets.items()},
    }


def print_report(score: dict[str, Any], failure_report: dict[str, Any]) -> None:
    print(json.dumps({"overall": score["overall"], "n": score["n"], "axes": score["axes"]}, ensure_ascii=False, indent=2))
    print("\nFailure counts:")
    for key, value in failure_report["failure_counts"].items():
        print(f"  {key}: {value}")
    print("\nResolver sources:")
    for key, value in failure_report["resolver_sources"].items():
        print(f"  {key}: {value}")
    print("\nTop plan mismatches:")
    for key, value in list(failure_report["plan_mismatches"].items())[:10]:
        print(f"  {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SCPC deterministic harness on dev data.")
    parser.add_argument("--candidate", default="candidate_001", help="Candidate/run name for reports.")
    parser.add_argument("--no-write", action="store_true", help="Do not write report files.")
    args = parser.parse_args()

    dev_tasks = load_jsonl(DATA_DIR / "dev_tasks.jsonl")
    dev_answers = load_json(DATA_DIR / "dev_answers.json")
    payload, harness = run_harness(
        dev_tasks,
        FinalHarness,
        harness_name=args.candidate,
        return_harness=True,
    )
    validate_payload(payload, {str(task["id"]) for task in dev_tasks})
    score = score_dev_submission(payload, dev_answers)
    failure_report = build_failure_report(dev_tasks, payload, dev_answers, harness.debug_traces, score["rows"])
    print_report(score, failure_report)

    if not args.no_write:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = REPORTS_DIR / f"{args.candidate}_{stamp}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "score.json").write_text(
            json.dumps({k: v for k, v in score.items() if k != "rows"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "rows.json").write_text(json.dumps(score["rows"], ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "failures.json").write_text(
            json.dumps(failure_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "payload_dev.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote reports: {out_dir}")


if __name__ == "__main__":
    main()


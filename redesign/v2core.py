"""Clean-room v2 core: bilingual grammar features + procedures + rule mining.

Everything here is derived from the 120 labeled dev pairs + TERMS_GUIDE. No content from
the evaluation inputs is used to define any lexicon entry, feature, or rule (evaluation
data only ever flows FORWARD through a frozen harness).

Layers (per the approved Part-11 plan):
  P — procedures: focal resolution via the shipped marker trace / candidate-list grammar.
  F — feature compiler: Korean clause concepts (canonical English tokens) + record enum
      slot grammar (values decomposed on '_' into reusable semantic tokens).
  R — thin rule layer mined from dev with support/purity ledger (no raw-string keys).

stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# ---------------------------------------------------------------- loading

def load_dev() -> tuple[list[dict], dict[str, dict]]:
    tasks = [json.loads(l) for l in (DATA / "dev_tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    answers = json.loads((DATA / "dev_answers.json").read_text(encoding="utf-8"))["answers"]
    return tasks, answers


def records_of(task: dict) -> list[dict]:
    return list((task.get("device_state") or {}).get("records") or [])


def objects_of(task: dict) -> list[dict]:
    return list((task.get("device_state") or {}).get("objects") or [])


def rec_value(task: dict, rtype: str):
    vals = [r.get("value") for r in records_of(task) if r.get("type") == rtype]
    return vals[-1] if vals else None


def has_rec(task: dict, rtype: str) -> bool:
    return any(r.get("type") == rtype for r in records_of(task))


# ---------------------------------------------------------------- sentences

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=다\.)|(?<=요\.)|(?<=함\.)|(?<=음\.)")


def sentences(task: dict) -> list[tuple[str, str]]:
    """(source, sentence) from prompt / history / personal_memory. Object bodies are NOT
    a directive source (they quote instructions inside message content)."""
    out: list[tuple[str, str]] = []
    for seg in SENT_SPLIT.split(str(task.get("prompt") or "")):
        if seg.strip():
            out.append(("prompt", seg.strip()))
    for h in task.get("visible_history") or []:
        text = str(h.get("summary") if isinstance(h, dict) else h)
        for seg in SENT_SPLIT.split(text):
            if seg.strip():
                out.append(("history", seg.strip()))
    for m in task.get("personal_memory") or []:
        text = str(m.get("text") if isinstance(m, dict) else m)
        for seg in SENT_SPLIT.split(text):
            if seg.strip():
                out.append(("memory", seg.strip()))
    return out


# ------------------------------------------------- Korean -> canonical tokens (lexicon)
# Tier-1 morpheme stems observed in the dev corpus, grouped by the English canonical
# concept they render. Single-eojeol stems wherever possible; every multi-word literal is
# verbatim-contained in the dev corpus (audit provenance check enforces this).

NEG_SEND = ("보내지 말", "공유하지 말", "전달 대신", "전달 동작은 취소", "보내는 작업은 취소", "외부 공유가 아니라", "바깥으로")
LOCAL_STATE = ("내부", "기기 안", "장치 안", "로컬", "상태만", "상태값만", "상태 기록", "처리 상태만")
UNCONFIRMED = ("확정되지 않", "미확정", "확인되지 않", "결론을 내릴 수 없", "불분명")
CONFIRM_FIRST = ("다시 확인", "먼저 확인", "사용자에게 먼저", "물어")
INVALIDATED = ("깨졌", "취소된", "사라졌", "무효화", "기대면 안")
STOP_CMD = ("멈춰야", "진행하면 안", "실행하면 안", "실행을 막", "처리하지 않")
REDACT_SUMMARY = ("제외한", "세부값")
SUMMARY_ONLY = ("요약만",)


def concept_of(sent: str) -> str | None:
    """Canonical concept of ONE corrective clause (English latent token)."""
    neg_send = any(t in sent for t in NEG_SEND)
    local = any(t in sent for t in LOCAL_STATE)
    if neg_send and local:
        return "LOCAL_COMMIT"
    if any(t in sent for t in INVALIDATED) and any(t in sent for t in STOP_CMD):
        return "HOLD_INVALID"
    if any(t in sent for t in REDACT_SUMMARY) and any(t in sent for t in SUMMARY_ONLY):
        return "REDACT_ONLY"
    if any(t in sent for t in UNCONFIRMED):
        return "ASK_FIRST"
    if any(t in sent for t in CONFIRM_FIRST) and ("지시" in sent or "명시" in sent):
        return "ASK_FIRST"
    return None


def directive_of(task: dict) -> str | None:
    """The latest corrective directive concept from the prompt's 단/다만 clauses."""
    concept = None
    for seg in SENT_SPLIT.split(str(task.get("prompt") or "")):
        s = seg.strip()
        if not s.startswith(("단,", "다만")):
            continue
        c = concept_of(s)
        if c:
            concept = c  # later clauses override earlier ones
    return concept


# ------------------------------------------------- enum slot grammar (English channel)

def enum_tokens(rtype: str, value) -> set[str]:
    """Decompose an enum-like record value into reusable semantic tokens. Unknown word
    pieces contribute nothing (never a guess)."""
    out: set[str] = set()
    if not isinstance(value, str) or not value:
        return out
    v = value.lower()
    words = set(v.replace("-", "_").split("_"))
    if rtype == "route_candidate_snapshot":
        if "local" in words or "internal" in words:
            out.add("RT_INT")
        if "external" in words:
            out.add("RT_EXT")
        if "single" in words or "only" in words:
            out.add("RT_UNIQUE")
    elif rtype == "dispatch_authority_check":
        if "confirmed" in words:
            out.add("AUTH_OK")
        if "pending" in words:
            out.add("AUTH_PENDING")
        if "incomplete" in words:
            out.add("AUTH_INCOMPLETE")
        if "local" in words:
            out.add("AUTH_LOCAL")
        if "internal" in words:
            out.add("AUTH_INTERNAL")
        if "user" in words:
            out.add("AUTH_USER")
    elif rtype == "share_boundary_update":
        if "local" in words or "update" in words and "boundary" in words and "local" in words:
            pass
        if "local" in words:
            out.add("BND_LOCAL")
        if "redacted" in words or "redact" in words:
            out.add("BND_REDACT")
        if "blocked" in words:
            out.add("BND_BLOCKED")
        if "external" in words:
            out.add("BND_EXT")
        if "selection" in words:
            out.add("BND_POST_SELECTION")
    elif rtype == "session_share_policy":
        if "strict" in words:
            out.add("POL_STRICT")
        if "normal" in words:
            out.add("POL_NORMAL")
    elif rtype == "consent":
        if "revoked" in v or "revok" in v:
            out.add("CONSENT_REVOKED")
    elif rtype == "route_binding_order":
        # X_after_Y: X arrived after Y (X is the fresher stage).
        if "_after_" in v:
            x, y = v.split("_after_", 1)
            out.add(f"FRESH_{x.upper()}")
            out.add(f"STALE_{y.upper()}")
    return out


# ------------------------------------------------- task feature compiler

RECORD_FLAG_TYPES = (
    "target_changed_after_turn", "memory_conflict", "payment_policy", "amount_changed",
    "merchant_verification", "duration_ambiguous", "calendar_conflict", "security_alert",
    "safety_mode", "ambiguous_target", "ambiguous_focal", "guardrail_ladder_signal",
    "persistent_memory_write", "persistent_memory_recall", "ops_memory_recall",
    "external_share_policy", "enterprise_policy_recall", "temporary_override_allowed",
    "privacy_guard", "trusted_subscription", "resolved_target",
)


def hist_flags(task: dict) -> set[str]:
    out: set[str] = set()
    for src, s in sentences(task):
        if src != "history":
            continue
        if "단정하지 말" in s and "사용자 확인" in s:
            out.add("HX_ASK_MIXED")
        if any(t in s for t in UNCONFIRMED) and any(t in s for t in CONFIRM_FIRST):
            out.add("HX_ASK_UNCONF")
    return out


def task_features(task: dict, session: dict | None = None) -> frozenset[str]:
    f: set[str] = set()
    d = directive_of(task)
    if d:
        f.add(f"DIR_{d}")
    f |= hist_flags(task)
    for rt in RECORD_FLAG_TYPES:
        if has_rec(task, rt):
            f.add(f"REC_{rt}")
    for r in records_of(task):
        rtype = str(r.get("type") or "")
        f |= enum_tokens(rtype, r.get("value"))
    # consent value may be nested
    cv = rec_value(task, "consent")
    if isinstance(cv, dict) and "revok" in json.dumps(cv):
        f.add("CONSENT_REVOKED")
    # avoid-item guard: a stored avoid preference appearing in the current prompt
    if session:
        avoid = session.get("avoid_items") or set()
        p = str(task.get("prompt") or "").lower()
        if any(a and a.lower() in p for a in avoid):
            f.add("MEM_AVOID_HIT")
    # base-request intent (prompt, non-corrective sentences)
    prompt = str(task.get("prompt") or "")
    if "결제" in prompt:
        f.add("REQ_PAY")
    if "저장해" in prompt or "기억해" in prompt:
        f.add("REQ_MEMWRITE")
    return frozenset(f)


def update_session(task: dict, session: dict) -> None:
    for r in records_of(task):
        if r.get("type") == "persistent_memory_write" and isinstance(r.get("value"), dict):
            v = r["value"]
            key = str(v.get("memory_key") or v.get("person") or "")
            if key:
                session.setdefault("profiles", {})[key] = v
            if v.get("avoid"):
                session.setdefault("avoid_items", set()).add(str(v["avoid"]))


# ------------------------------------------------- focal procedures (layer P)

ORDINAL = {"첫 번째": 0, "첫번째": 0, "둘째": 1, "두 번째": 1, "두번째": 1, "세 번째": 2, "세번째": 2, "셋째": 2, "가운데": -100, "중간": -100, "마지막": -1}
KEEP = ("확정", "승인", "유효", "처리 대상", "기준 참조", "우선")
DROP = ("제외", "보류 후보", "배제")
CODE = re.compile(r"WM-\d+|marker_[a-z]+|masked_ref")


def resolve_focal(task: dict) -> str | None:
    objs = objects_of(task)
    by_ref = {str((o.get("attrs") or {}).get("ref_code") or ""): str(o.get("id")) for o in objs}

    # P1 — shipped marker-trace procedure (TERMS_GUIDE): latest_phase -> phase_to_marker
    # -> marker_to_ref -> ref_code -> object id.
    trace = rec_value(task, "focal_resolution_trace")
    refs = rec_value(task, "focal_marker_refs")
    if isinstance(trace, dict) and isinstance(refs, dict):
        phase = trace.get("latest_phase")
        p2m = trace.get("phase_to_marker") or {}
        m2r = refs.get("marker_to_ref") or {}
        marker = p2m.get(str(phase)) if phase is not None else None
        ref = m2r.get(str(marker)) if marker else None
        if ref and str(ref) in by_ref:
            return by_ref[str(ref)]

    # P2 — candidate-list grammar over history sentences (designation / approval /
    # ordinal / exclusion). Conjuncts are split FIRST so a keep-verb and a drop-verb in
    # one sentence each govern only their own ordinals/codes; later statements win.
    chosen: str | None = None
    excluded: set[str] = set()
    excluded_idx: set[int] = set()
    ordered: list[str] = []
    for src, s in sentences(task):
        if src == "memory":
            continue
        codes_all = CODE.findall(s)
        if len(codes_all) >= 3 and ("순서" in s or "/" in s):
            ordered = codes_all
        for seg in re.split(r"(?<=고),\s*|(?<=지만)\s+", s):
            codes = CODE.findall(seg)
            ords = [idx for m_ord, idx in ORDINAL.items() if m_ord in seg]
            drop = any(t in seg for t in DROP)
            keep = any(t in seg for t in KEEP)
            if drop and not keep:
                excluded.update(codes)
                excluded_idx.update(o for o in ords if o >= 0)
                continue
            if keep:
                picked = None
                pick_ords = [o for o in ords if o not in excluded_idx]
                if pick_ords:
                    src_list = ordered or codes_all
                    if src_list:
                        o = pick_ords[0]
                        if o == -100:
                            picked = src_list[len(src_list) // 2]
                        elif -len(src_list) <= o < len(src_list):
                            picked = src_list[o]
                if picked is None and codes:
                    kept = [c for c in codes if c not in excluded]
                    picked = kept[-1] if kept else None
                if picked:
                    chosen = picked
    if chosen:
        marker_map = rec_value(task, "focal_marker_refs")
        if chosen.startswith("marker_") and isinstance(marker_map, dict):
            ref = (marker_map.get("marker_to_ref") or {}).get(chosen)
            if ref and str(ref) in by_ref:
                return by_ref[str(ref)]
        if chosen in by_ref:
            return by_ref[chosen]

    # P3 — single unambiguous object of a type the prompt asks about.
    if len(objs) == 1:
        return str(objs[0].get("id"))
    return None


# ------------------------------------------------- target selectors (typed, no literals)

def target_selectors(task: dict, focal_id: str | None, session: dict | None) -> dict[str, str]:
    sels: dict[str, str] = {"MEMORY_STORE": "memory_store", "USER": "user"}
    rt = rec_value(task, "resolved_target")
    if isinstance(rt, str) and rt:
        sels["RESOLVED"] = rt
    elif isinstance(rt, dict):
        for k in ("target", "route", "value", "name", "recipient"):
            if isinstance(rt.get(k), str) and rt[k]:
                sels["RESOLVED"] = rt[k]
                break
    tchg = rec_value(task, "target_changed_after_turn")
    if isinstance(tchg, str) and tchg and not tchg.startswith("prior_"):
        sels["TCHG"] = tchg
    focal = next((o for o in objects_of(task) if str(o.get("id")) == focal_id), None)
    attrs = (focal or {}).get("attrs") or {}
    for k in ("recipient", "attendee", "merchant", "owner"):
        if isinstance(attrs.get(k), str) and attrs[k]:
            sels["FOCAL_ATTR"] = attrs[k]
            break
    # recalled person profile channels (session-accumulated writes)
    rec = rec_value(task, "persistent_memory_recall")
    prof = None
    if isinstance(rec, dict) and session:
        key = str(rec.get("memory_key") or rec.get("person") or "")
        prof = (session.get("profiles") or {}).get(key)
    if isinstance(prof, dict):
        for name, key in (("MEM_PREF", "preferred_channel"), ("MEM_HEALTH", "health_channel"),
                          ("MEM_APPROVAL", "approval_channel"), ("MEM_CHECKUP", "checkup_place")):
            if prof.get(key):
                sels[name] = str(prof[key])
    return sels


# ------------------------------------------------- rule mining (layer R)

def compute_features(tasks: list[dict]) -> tuple[dict[str, frozenset[str]], dict[str, dict]]:
    """Session-ordered feature computation; returns per-task features and the session
    state snapshot AS OF each task (for selector resolution)."""
    feats: dict[str, frozenset[str]] = {}
    snap: dict[str, dict] = {}
    sessions: dict[str, dict] = {}
    for t in sorted(tasks, key=lambda x: (str(x.get("session_id")), int(x.get("turn_index") or 0), str(x.get("id")))):
        s = sessions.setdefault(str(t.get("session_id")), {})
        feats[str(t["id"])] = task_features(t, s)
        snap[str(t["id"])] = {"profiles": dict(s.get("profiles") or {}), "avoid_items": set(s.get("avoid_items") or set())}
        update_session(t, s)
    return feats, snap


# Directive concepts decide control outright (dev purity 1.0, support 33/11/6/2).
DIR_CONTROL = {"DIR_LOCAL_COMMIT": "proceed", "DIR_ASK_FIRST": "ask",
               "DIR_HOLD_INVALID": "hold", "DIR_REDACT_ONLY": "amend"}


def mine_control_rules(train_ids: list[str], feats: dict[str, frozenset[str]],
                       answers: dict[str, dict], min_support: int = 2):
    """Greedy decision list over feature singletons and pairs (RIPPER-lite): repeatedly
    take the pure rule with the largest remaining coverage. No raw enum/string keys —
    features only. Directive tasks are excluded (handled by DIR_CONTROL)."""
    remaining = [tid for tid in train_ids
                 if tid in answers and not any(df in feats[tid] for df in DIR_CONTROL)]
    rules: list[tuple[frozenset[str], str, int]] = []
    while True:
        stat: dict[frozenset[str], Counter] = defaultdict(Counter)
        for tid in remaining:
            fs = sorted(feats[tid])
            c = answers[tid]["control"]
            for i, a in enumerate(fs):
                stat[frozenset([a])][c] += 1
                for b in fs[i + 1:]:
                    stat[frozenset([a, b])][c] += 1
        best = None
        for key, cnt in stat.items():
            total = sum(cnt.values())
            top, n = cnt.most_common(1)[0]
            if n == total and total >= min_support:
                cand = (total, -len(key), key, top)
                if best is None or cand > best:
                    best = cand
        if best is None:
            break
        total, _neglen, key, top = best
        rules.append((key, top, total))
        remaining = [tid for tid in remaining if not key <= feats[tid]]
        if not remaining:
            break
    default = "proceed"
    if remaining:
        default = Counter(answers[tid]["control"] for tid in remaining).most_common(1)[0][0]
    return rules, default


def predict_control(f: frozenset[str], rules, default: str) -> str:
    for df, c in DIR_CONTROL.items():
        if df in f:
            return c
    for key, c, _n in rules:
        if key <= f:
            return c
    return default


# ------------------------------------------------- target rule mining

def target_context(f: frozenset[str], control: str) -> str:
    return f"{control}|{'DIR' if any(d in f for d in DIR_CONTROL) else 'REC'}"


def mine_target_priority(train_ids: list[str], tasks_by_id: dict[str, dict],
                         feats: dict[str, frozenset[str]], snap: dict[str, dict],
                         answers: dict[str, dict], focal_of: dict[str, str | None]):
    """Per (control, directive?) context: greedy selector priority list."""
    ctx_tasks: dict[str, list[str]] = defaultdict(list)
    sels_cache: dict[str, dict[str, str]] = {}
    for tid in train_ids:
        if tid not in answers:
            continue
        c = answers[tid]["control"]
        ctx_tasks[target_context(feats[tid], c)].append(tid)
        sels_cache[tid] = target_selectors(tasks_by_id[tid], focal_of.get(tid), snap[tid])
    priority: dict[str, list[str]] = {}
    for ctx, tids in ctx_tasks.items():
        remaining = list(tids)
        order: list[str] = []
        sel_names = {"MEMORY_STORE", "USER", "RESOLVED", "TCHG", "FOCAL_ATTR",
                     "MEM_PREF", "MEM_HEALTH", "MEM_APPROVAL", "MEM_CHECKUP"}
        while remaining:
            best = None
            for name in sorted(sel_names - set(order)):
                hits = [tid for tid in remaining
                        if sels_cache[tid].get(name) == answers[tid]["target"]]
                applicable = [tid for tid in remaining if name in sels_cache[tid]]
                if applicable and len(hits) == len(applicable) and hits:
                    cand = (len(hits), name)
                    if best is None or cand > best:
                        best = cand
            if best is None:
                break
            _n, name = best
            order.append(name)
            remaining = [tid for tid in remaining if name not in sels_cache[tid]]
        priority[ctx] = order
    return priority


def predict_target(task: dict, f: frozenset[str], control: str, focal_id: str | None,
                   session: dict | None, priority: dict[str, list[str]]) -> str:
    sels = target_selectors(task, focal_id, session)
    for name in priority.get(target_context(f, control), []):
        if name in sels:
            return sels[name]
    for name in ("RESOLVED", "FOCAL_ATTR", "USER"):
        if name in sels:
            return sels[name]
    return "user"


def evaluate(train_ids: list[str], test_ids: list[str], tasks_by_id, feats, snap, answers,
             focal_of) -> tuple[int, int, int, int]:
    """Mine on train, answer test; return (focal_ok, target_ok, control_ok, gate_ok)."""
    rules, default = mine_control_rules(train_ids, feats, answers)
    prio = mine_target_priority(train_ids, tasks_by_id, feats, snap, answers, focal_of)
    fo = to = co = go = 0
    for tid in test_ids:
        ref = answers[tid]
        f = feats[tid]
        focal = focal_of[tid]
        control = predict_control(f, rules, default)
        target = predict_target(tasks_by_id[tid], f, control, focal, snap[tid], prio)
        okf = focal == ref["focal_id"]
        okt = target == ref["target"]
        okc = control == ref["control"]
        fo += okf
        to += okt
        co += okc
        go += okf and okt and okc
    return fo, to, co, go


if __name__ == "__main__":
    tasks, answers = load_dev()
    tasks_by_id = {str(t["id"]): t for t in tasks}
    ids = list(tasks_by_id)
    feats, snap = compute_features(tasks)
    focal_of = {tid: resolve_focal(tasks_by_id[tid]) for tid in ids}

    fo = sum(1 for tid in ids if focal_of[tid] == answers[tid]["focal_id"])
    print(f"[focal] procedures: {fo}/{len(ids)}")

    fo, to, co, go = evaluate(ids, ids, tasks_by_id, feats, snap, answers, focal_of)
    print(f"[full-dev] focal {fo}/120  target {to}/120  control {co}/120  GATE {go}/120")

    # --- LOSO (leave-one-session-out)
    by_sess: dict[str, list[str]] = defaultdict(list)
    for tid in ids:
        by_sess[str(tasks_by_id[tid].get("session_id"))].append(tid)
    tot = Counter()
    for sess, test in sorted(by_sess.items()):
        train = [tid for tid in ids if str(tasks_by_id[tid].get("session_id")) != sess]
        r = evaluate(train, test, tasks_by_id, feats, snap, answers, focal_of)
        tot.update(dict(zip("ftcg", r)))
    print(f"[LOSO]     focal {tot['f']}/120  target {tot['t']}/120  control {tot['c']}/120  GATE {tot['g']}/120")

    # --- LOEO (leave-one-enum-value-out): hold out every task carrying the value
    enum_types = ("dispatch_authority_check", "share_boundary_update",
                  "route_candidate_snapshot", "route_binding_order", "session_share_policy")
    values: set[tuple[str, str]] = set()
    for t in tasks:
        for r in records_of(t):
            if r.get("type") in enum_types and isinstance(r.get("value"), str):
                values.add((r["type"], r["value"]))
    print("[LOEO] per held-out enum value (gate on held tasks):")
    agg_g = agg_n = 0
    for rtype, val in sorted(values):
        test = [tid for tid in ids if any(
            r.get("type") == rtype and r.get("value") == val for r in records_of(tasks_by_id[tid]))]
        train = [tid for tid in ids if tid not in set(test)]
        f2, t2, c2, g2 = evaluate(train, test, tasks_by_id, feats, snap, answers, focal_of)
        agg_g += g2
        agg_n += len(test)
        print(f"   {rtype[:28]:28} {val[:36]:36} n={len(test):3} gate={g2}/{len(test)}")
    print(f"[LOEO] aggregate gate: {agg_g}/{agg_n} = {agg_g/max(agg_n,1):.3f}")
    sys.exit(0)

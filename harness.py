from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUBMISSION_SCHEMA = "scpc.final.answer.v1"
FIXED_SLM_ID = "scpc-final-fixed-slm-local-facade"

VALID_CONTROLS = {"proceed", "amend", "hold", "ask"}
VALID_SCOPE_MODES = {"raw", "summary", "redacted", "status_only", "none"}

# A share_boundary_update whose name denotes a redact-and-dispatch directive maps to
# amend (redact then share), not to an ambiguity to clarify. Matched by the "redact"
# stem so the rule is structural (any redact-boundary), not an enumerated value list.
def is_redaction_directive(boundary: str) -> bool:
    b = str(boundary or "")
    return "redact" in b and "boundary" in b


# Route-candidate classification by structural stems (not enumerated values), so new
# route values generalize: a "local"-only candidate set stays internal; any route that
# includes an "external" candidate is an outward-share situation.
def route_is_local_only(route: str) -> bool:
    r = str(route or "")
    return "local" in r and "external" not in r


def route_has_external(route: str) -> bool:
    r = str(route or "")
    return "external" in r


# Authority / boundary classification by the same structural-stem principle: an authority
# state is "confirmed" when it carries the confirmed stem, a dispatch is "blocked", and a
# boundary is a local-update one by the matching stem — so unseen values of the same shape
# generalize instead of being missed by an enumerated value list.
def authority_confirmed(value: Any) -> bool:
    return isinstance(value, str) and value.endswith("_confirmed")


def dispatch_blocked(value: Any) -> bool:
    return isinstance(value, str) and "blocked" in value


def is_local_boundary(value: Any) -> bool:
    v = str(value or "")
    return "local" in v and "boundary" in v


# --- Directive intent vocabulary ---
# A request often ends with a corrective directive ("단, …") that overrides the default
# action. There are four intents; each has a bounded, general Korean vocabulary for the
# CONCEPT (stop / confirm / keep-local / redact). Precedence: keep-local, then stop, then
# confirm, then redact (an explicit "internal state only" correction is unambiguous;
# a stop/precondition-broken signal outranks a confirm; redact is the mildest).
INTENT_LOCAL_STATE = (
    "내부 상태", "내부 기록", "내부 업데이트", "내부 처리", "기기 안", "기기 내부",
    "장치 안", "장치 내부", "로컬", "상태만", "상태값만", "완료 상태만",
)
INTENT_LOCAL_NEG = (
    "보내지 말", "공유하지 말", "전달하지 말", "전송하지", "전달 대신", "바깥으로",
    "외부로 보내", "외부 전송을 하지", "전달 동작은 취소", "보내는 작업은 취소",
)
INTENT_STOP = (
    "멈추", "멈춰", "중단", "정지", "차단", "보류", "막아", "막는", "그만",
    "무효", "파기", "깨졌", "깨진", "깨뜨", "무너", "뒤집", "사라", "신뢰할 수 없",
    "믿을 수 없", "위험", "하면 안", "하지 말", "기대면 안", "조건이 취소", "승인이 취소",
)
INTENT_CONFIRM = (
    "확인 절차", "확인 필요", "재확인", "다시 확인", "먼저 확인", "확인을 받", "확인해야",
    "확인 질문", "확인되지 않", "물어", "여쭤", "질문", "미확정", "불확실", "불분명",
    "애매", "모호", "확정되지 않", "확정 정보가 없", "결론을 내릴 수 없", "판단할 수 없",
    "clarification", "현재 정보만으로는",
)
INTENT_REDACT = (
    "요약만", "요약 수준", "익명", "마스킹", "제거", "제외", "덜어", "최소 요약",
    "정제된 요약", "민감", "원문 제외", "세부값을 제외", "세부는 제외",
    "포함하지 않", "포함하지 말",
)

SENSITIVE_FIELDS = {
    "raw_quote",
    "rrn",
    "name",
    "location",
    "numeric_value",
    "doctor_note",
    "card_number",
    "amount",
    "age",
    "raw_memory",
}

# Non-channel targets: the only destinations that are NOT an outward/external channel.
# Anything else that resolves as a target is a named external destination — judged
# structurally so unseen channel names generalize (no hardcoded channel list).
INTERNAL_TARGETS = {"", "memory_store", "user"}


def is_external_channel(target: Any) -> bool:
    return isinstance(target, str) and target not in INTERNAL_TARGETS


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_submission_csv(payload: dict[str, Any], path: Path) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["submission"])
        writer.writerow([json.dumps(payload, ensure_ascii=False, separators=(",", ":"))])


def csv_round_trip(path: Path) -> dict[str, Any]:
    import csv
    import sys

    csv.field_size_limit(sys.maxsize)

    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 1 or "submission" not in rows[0]:
        raise ValueError("submission.csv must contain one data row with a submission column")
    return json.loads(rows[0]["submission"])


def records_of(task: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((task.get("device_state") or {}).get("records") or []))


def objects_of(task: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((task.get("device_state") or {}).get("objects") or []))


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def object_text(obj: dict[str, Any]) -> str:
    attrs = obj.get("attrs") or {}
    return " ".join(
        [
            str(obj.get("id", "")),
            str(obj.get("type", "")),
            text_of(attrs),
        ]
    ).lower()


def flatten_strings(value: Any) -> list[str]:
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for item in value.values():
            out.extend(flatten_strings(item))
        return out
    if isinstance(value, list):
        for item in value:
            out.extend(flatten_strings(item))
        return out
    return [str(value)]


def wm_codes(text: str) -> list[str]:
    return re.findall(r"WM-\d{4}", text)


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


@dataclass
class TaskContext:
    task: dict[str, Any]
    session: dict[str, Any]
    objects: list[dict[str, Any]] = field(init=False)
    records: list[dict[str, Any]] = field(init=False)
    by_id: dict[str, dict[str, Any]] = field(init=False)
    by_ref: dict[str, dict[str, Any]] = field(init=False)
    by_type: dict[str, list[dict[str, Any]]] = field(init=False)
    trace: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.objects = objects_of(self.task)
        self.records = records_of(self.task)
        self.by_id = {str(o.get("id")): o for o in self.objects if o.get("id")}
        self.by_ref = {}
        self.by_type = defaultdict(list)
        for obj in self.objects:
            self.by_type[str(obj.get("type") or "")].append(obj)
            ref = str((obj.get("attrs") or {}).get("ref_code") or "")
            if ref:
                self.by_ref[ref] = obj
        self.trace["record_set"] = "|".join(sorted({str(r.get("type")) for r in self.records}))

    @property
    def prompt(self) -> str:
        return str(self.task.get("prompt") or "")

    @property
    def history_text(self) -> str:
        return " ".join(text_of(item) for item in self.task.get("visible_history", []) or [])

    @property
    def records_text(self) -> str:
        return " ".join(text_of(r.get("value")) for r in self.records)

    @property
    def all_text(self) -> str:
        return " ".join([self.prompt, self.history_text, self.records_text]).lower()

    def values(self, record_type: str) -> list[Any]:
        return [r.get("value") for r in self.records if r.get("type") == record_type]

    def value(self, record_type: str, default: Any = None) -> Any:
        values = self.values(record_type)
        return values[-1] if values else default

    def has_record(self, record_type: str) -> bool:
        return any(r.get("type") == record_type for r in self.records)

    def contains_value(self, token: str) -> bool:
        needle = token.lower()
        return needle in self.all_text

    def confirmed_channel(self) -> str | None:
        """The external channel this turn is bound to: its own resolved_target when that
        names an external destination, else None."""
        rv = self.value("resolved_target")
        if isinstance(rv, str) and is_external_channel(rv):
            return rv
        if isinstance(rv, dict):
            for key in ("target", "route", "value", "name", "recipient"):
                if is_external_channel(rv.get(key)):
                    return str(rv[key])
        return None


class TaskNormalizer:
    def normalize(self, task: dict[str, Any], session: dict[str, Any]) -> TaskContext:
        return TaskContext(task=task, session=session)


class FocalResolver:
    def resolve(self, ctx: TaskContext) -> dict[str, Any]:
        return (
            self._from_direct_object_id(ctx)
            or self._from_marker_trace(ctx)
            or self._from_history_semantic_list(ctx)
            or self._from_record_ref_code(ctx)
            or self._from_prompt_overlap(ctx)
            or (ctx.objects[0] if ctx.objects else {})
        )

    def _select(self, ctx: TaskContext, obj: dict[str, Any], source: str, **extra: Any) -> dict[str, Any]:
        ctx.trace.update({"resolver_source": source, "focal_id": obj.get("id"), **extra})
        return obj

    def _from_direct_object_id(self, ctx: TaskContext) -> dict[str, Any] | None:
        for record in reversed(ctx.records):
            for token in flatten_strings(record.get("value")):
                if token in ctx.by_id:
                    return self._select(ctx, ctx.by_id[token], "direct_object_id", direct_ref=token)
        return None

    def _from_marker_trace(self, ctx: TaskContext) -> dict[str, Any] | None:
        refs = ctx.value("focal_marker_refs")
        trace = ctx.value("focal_resolution_trace")
        if not isinstance(refs, dict) or not isinstance(trace, dict):
            return None
        marker_to_ref = refs.get("marker_to_ref") or {}
        phase_to_marker = trace.get("phase_to_marker") or {}
        latest_phase = trace.get("latest_phase")
        phase_source = str(trace.get("phase_source") or "")

        if not latest_phase and phase_source:
            latest_phase = self._phase_from_route_order(ctx.value(phase_source))
        marker = phase_to_marker.get(latest_phase)
        ref_code = marker_to_ref.get(marker)
        obj = ctx.by_ref.get(str(ref_code))
        if obj:
            return self._select(
                ctx,
                obj,
                "focal_resolution_trace",
                selected_phase=latest_phase,
                selected_marker=marker,
                selected_ref_code=ref_code,
            )
        return None

    def _phase_from_route_order(self, value: Any) -> str | None:
        mapping = {
            "authority_after_boundary": "authority",
            "boundary_after_authority": "boundary",
            "candidates_after_authority": "authority",
        }
        return mapping.get(str(value))

    # --- Delimiter/phrasing-agnostic semantic candidate-list resolver ---
    # A history that lists candidate refs marks the focal one of two ways: an ordinal
    # into the listed order, or an approval marker bound to one specific code. We parse
    # that meaning structurally so the resolver is robust to surface variation
    # (delimiters ",", "/", "다음"; ordinal wording; approval-marker wording) rather
    # than matching fixed phrases.

    APPROVE_MARKERS = ("최종 승인", "승인 표시", "승인 상태", "통과", "유효", "유지", "focal")
    EXCLUDE_MARKERS = ("제외", "배제", "보류", "후보군", "나머지", "남겼")
    SELECT_VERBS = ("처리 대상", "선택", "확정", "유효", "focal", "통과")
    ORDINAL_FORMS = (
        (r"첫째|첫\s*번째|첫번째", 0),
        (r"둘째|두\s*번째|두번째", 1),
        (r"셋째|세\s*번째|세번째", 2),
        (r"넷째|네\s*번째|네번째", 3),
        (r"다섯째|다섯\s*번째", 4),
        (r"여섯째|여섯\s*번째", 5),
    )

    @staticmethod
    def _clauses(text: str) -> list[str]:
        parts = re.split(r"[,\.。]|남았고|남겼고|보이지만|했고|이고(?=\s)", text)
        return [p.strip() for p in parts if p.strip()]

    # A single operative reference code is often designated by a copula subject
    # ("… 참조는/코드는/대상은/ref는/binding은 WM-X"). Match the subject→code binding
    # structurally rather than by fixed phrases.
    _COPULA = re.compile(r"(?:것은|참조는|항목은|후보는|코드는|ref는|binding은|대상은)\s*(WM-\d{4})")

    def _approved_pick(self, text: str) -> str | None:
        """Type B / single-code designation: one code is marked approved/operative,
        bound by copula ("…참조는/코드는/ref는 WM-X"), by "X만 통과", or by proximity
        to an approval marker. Latest such designation wins."""
        picked: str | None = None
        for clause in self._clauses(text):
            code = None
            match = self._COPULA.search(clause)
            if match:
                code = match.group(1)
            if code is None:
                match = re.search(r"(WM-\d{4})\s*만\s*(?:통과|승인|유효)", clause)
                if match:
                    code = match.group(1)
            if code is None and any(marker in clause for marker in self.APPROVE_MARKERS):
                for marker in self.APPROVE_MARKERS:
                    match = re.search(re.escape(marker) + r"[^A-Z]{0,12}?(WM-\d{4})", clause)
                    if match:
                        code = match.group(1)
                        break
            if code is not None and not any(e in clause for e in self.EXCLUDE_MARKERS):
                picked = code
        return picked

    def _ordinal_index(self, clause: str, count: int) -> int | None:
        for pattern, idx in self.ORDINAL_FORMS:
            if re.search(pattern, clause):
                return idx
        if re.search(r"가운데|중간", clause):
            return 1 if count == 3 else None
        if "마지막" in clause:
            return count - 1
        return None

    def _ordinal_pick(self, text: str, codes: list[str]) -> tuple[str, int] | None:
        """Type A: ordinal selector bound to a positive-selection clause."""
        chosen: tuple[str, int] | None = None
        for clause in self._clauses(text):
            if not any(verb in clause for verb in self.SELECT_VERBS):
                continue
            if any(marker in clause for marker in self.EXCLUDE_MARKERS):
                continue
            idx = self._ordinal_index(clause, len(codes))
            if idx is not None and 0 <= idx < len(codes):
                chosen = (codes[idx], idx)
        return chosen

    def _from_history_semantic_list(self, ctx: TaskContext) -> dict[str, Any] | None:
        text = " ".join([ctx.prompt, ctx.history_text])
        codes = ordered_unique(wm_codes(text))
        if not codes:
            return None
        approved = self._approved_pick(text)
        if approved:
            obj = ctx.by_ref.get(approved)
            if obj:
                return self._select(ctx, obj, "history_approved_marker", selected_ref_code=approved)
        ordinal = self._ordinal_pick(text, codes)
        if ordinal:
            ref_code, idx = ordinal
            obj = ctx.by_ref.get(ref_code)
            if obj:
                return self._select(
                    ctx, obj, "history_ordinal", selected_ref_code=ref_code, selected_index=idx
                )
        return None

    def _from_record_ref_code(self, ctx: TaskContext) -> dict[str, Any] | None:
        ignored = {"resolved_target", "ambiguous_target", "session_share_policy"}
        for record in reversed(ctx.records):
            if record.get("type") in ignored:
                continue
            for token in flatten_strings(record.get("value")):
                for ref_code in wm_codes(token):
                    obj = ctx.by_ref.get(ref_code)
                    if obj:
                        return self._select(ctx, obj, "record_ref_code", selected_ref_code=ref_code)
        return None

    def _from_prompt_overlap(self, ctx: TaskContext) -> dict[str, Any] | None:
        if not ctx.objects:
            return None
        type_preference = self._type_preference(ctx)
        if type_preference:
            candidates = ctx.by_type.get(type_preference) or []
            if candidates:
                return self._select(ctx, self._best_target_aligned(ctx, candidates), "type_preference")
        prompt_tokens = {
            tok
            for tok in re.findall(r"[A-Za-z0-9가-힣_]+", ctx.prompt.lower())
            if len(tok) >= 2
        }
        best = ctx.objects[0]
        best_score = -1
        for obj in ctx.objects:
            obj_text = object_text(obj)
            score = sum(1 for tok in prompt_tokens if tok in obj_text)
            attrs = obj.get("attrs") or {}
            if attrs.get("request_hint"):
                score += 1
            if obj.get("type") == "message" and "보내" in ctx.prompt:
                score += 1
            if score > best_score:
                best = obj
                best_score = score
        return self._select(ctx, best, "prompt_overlap", overlap_score=best_score)

    def _type_preference(self, ctx: TaskContext) -> str | None:
        prompt = ctx.prompt
        if any(token in prompt for token in ("메시지", "보내줘", "발송", "수신처", "recipient")):
            if ctx.by_type.get("message"):
                return "message"
        if any(token in prompt for token in ("결제", "송금", "금액", "merchant")):
            if ctx.by_type.get("payment_request"):
                return "payment_request"
        if any(token in prompt for token in ("조명", "루틴", "켜", "꺼", "IoT", "iot")):
            if ctx.by_type.get("iot_routine"):
                return "iot_routine"
            if ctx.by_type.get("device_setting"):
                return "device_setting"
        if any(token in prompt for token in ("일정", "회의", "calendar", "캘린더")):
            if ctx.by_type.get("calendar_event"):
                return "calendar_event"
        if any(token in prompt for token in ("건강", "복약", "검진", "doctor")):
            if ctx.by_type.get("health_record"):
                return "health_record"
        return None

    def _best_target_aligned(self, ctx: TaskContext, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        resolved = ctx.value("resolved_target")
        target_text = text_of(resolved).lower()
        if target_text:
            for obj in candidates:
                attrs = obj.get("attrs") or {}
                attrs_text = " ".join(
                    str(attrs.get(key) or "")
                    for key in ("recipient", "target", "channel", "app", "merchant", "attendee", "owner", "name")
                ).lower()
                if target_text in attrs_text:
                    return obj
        def score(obj: dict[str, Any]) -> int:
            attrs = obj.get("attrs") or {}
            body = text_of(attrs).lower()
            value = 0
            # Prefer the freshly-confirmed / current candidate over a stale, pre-existing
            # one, using general recency-and-confirmation vocabulary rather than any
            # task-specific content string.
            for token in ("방금", "최근", "확정", "현재"):
                if token in body:
                    value += 2
            if attrs.get("request_hint"):
                value += 3
            field_text = " ".join(flatten_strings(attrs.get("fields")) + flatten_strings(attrs.get("contains")))
            if "doctor_note" in field_text:
                value += 1
            for token in ("기존", "지난", "과거", "이전"):
                if token in body:
                    value -= 5
            return value

        return max(candidates, key=score)


class TargetResolver:
    def resolve(
        self,
        ctx: TaskContext,
        focal: dict[str, Any],
        decision_hint: str | None = None,
        memory: dict[str, Any] | None = None,
    ) -> str:
        if self._explicit_memory_store(ctx):
            return "memory_store"

        recalled = self._target_from_recalled_memory(ctx, memory or {})
        if recalled:
            return recalled

        changed = ctx.value("target_changed_after_turn")
        if isinstance(changed, str) and changed and not changed.startswith("prior_"):
            return changed

        resolved = ctx.value("resolved_target")
        if isinstance(resolved, dict):
            for key in ("target", "route", "value", "name", "recipient"):
                if resolved.get(key):
                    return str(resolved[key])
        if isinstance(resolved, str) and resolved:
            return resolved

        # No destination is stated on this turn: take it from the focal object's own
        # recipient/channel attributes, else fall back to the user.
        attrs = focal.get("attrs") or {}
        for key in ("recipient", "target", "channel", "app", "merchant", "attendee", "name", "owner"):
            if attrs.get(key):
                return str(attrs[key])
        return str(ctx.session.get("last_target") or "user")

    # Local-only intent = "update internal/device state, do not send externally".
    # Vocabulary is the general concept: an internal-state marker plus (optionally) an
    # external-send negation — plain concept words (내부/기기/장치/상태/로컬,
    # 보내지 말/공유하지 말/전달 대신).
    _INTERNAL_STATE_TOKENS = (
        "내부 상태", "기기 내부", "기기 안", "장치 안", "내부 업데이트",
        "내부 기록", "로컬 상태", "상태만 갱신", "상태값만", "상태만 기록",
        "local update", "local_update",
    )
    _EXTERNAL_NEG_TOKENS = (
        "보내지 말", "공유하지 말", "전달 대신", "전달 동작은 취소",
        "보내는 작업은 취소", "바깥으로",
    )

    def _explicit_memory_store(self, ctx: TaskContext) -> bool:
        if ctx.has_record("persistent_memory_write"):
            return True
        text = ctx.prompt.lower()
        if any(tok.lower() in text for tok in self._INTERNAL_STATE_TOKENS):
            return True
        # "don't send externally" + a state cue also denotes a local-only correction.
        if any(tok.lower() in text for tok in self._EXTERNAL_NEG_TOKENS) and "상태" in text:
            return True
        return False

    def _target_from_recalled_memory(self, ctx: TaskContext, memory: dict[str, Any]) -> str | None:
        recall_values = ctx.values("persistent_memory_recall")
        if not recall_values:
            return None
        recalled: dict[str, Any] = {}
        for value in recall_values:
            key = ""
            if isinstance(value, dict):
                key = str(value.get("memory_key") or value.get("person") or "")
                recalled.update(value)
            elif isinstance(value, str):
                key = value
            if key and isinstance(memory.get(key), dict):
                recalled.update(memory[key])
        if not recalled:
            personal = ctx.task.get("personal_memory")
            if isinstance(personal, dict):
                recalled.update(personal)
        if not recalled:
            return None
        prompt = ctx.prompt
        if ctx.has_record("safety_mode") and recalled.get("dusk_room"):
            return str(recalled["dusk_room"])
        if ctx.has_record("enterprise_policy_recall") and recalled.get("approval_channel"):
            return str(recalled["approval_channel"])
        if any(token in prompt for token in ("검진", "점검", "복약", "건강")):
            for key in ("preferred_channel", "health_channel", "care_channel", "checkup_place", "approval_channel"):
                if recalled.get(key):
                    return str(recalled[key])
        if any(token in prompt for token in ("생일", "선물", "연락", "쿠폰", "취향", "말투")):
            for key in ("preferred_channel", "health_channel"):
                if recalled.get(key):
                    return str(recalled[key])
        if any(token in prompt for token in ("지난번 성공", "성공한 방식", "지난 성공")):
            for key in ("last_success_target", "approval_channel", "preferred_channel"):
                if recalled.get(key):
                    return str(recalled[key])
        return None



@dataclass
class Decision:
    decision_class: str
    control: str
    reason: str
    # True when the class came from an explicit user directive (vs a record signal).
    # Target resolution uses this: a directive-driven ask/hold responds to the user;
    # a record-driven ask/hold keeps the channel the operation was headed to.
    from_directive: bool = False


class DecisionEngine:
    def _directive_intent(self, ctx: TaskContext) -> str | None:
        """Decision class from the request's trailing corrective directive. The latest
        user instruction is authoritative (a general recency principle); its intent is
        read from general concept vocabulary."""
        prompt = ctx.prompt
        clause = prompt.split("단,")[-1] if "단," in prompt else ""
        if not clause.strip():
            return None
        if any(t in clause for t in INTENT_LOCAL_STATE):
            return "local_update"
        if any(t in clause for t in INTENT_LOCAL_NEG) and "상태" in clause:
            return "local_update"
        if any(t in clause for t in INTENT_STOP):
            return "guard"
        if any(t in clause for t in INTENT_CONFIRM):
            return "clarify"
        if any(t in clause for t in INTENT_REDACT):
            return "minimal_disclosure"
        return None

    def decide(
        self, ctx: TaskContext, focal: dict[str, Any], target: str, memory: dict[str, Any] | None = None
    ) -> Decision:
        text = ctx.all_text
        explicit_local = TargetResolver()._explicit_memory_store(ctx)
        boundary = str(ctx.value("share_boundary_update") or "")
        authority = str(ctx.value("dispatch_authority_check") or "")
        route_snapshot = str(ctx.value("route_candidate_snapshot") or "")

        # The latest corrective directive, when present, sets the action. A decision
        # from the directive is marked so target resolution responds to the user.
        directive = self._directive_intent(ctx)
        if directive == "guard":
            return self._decision(ctx, "guard", "hold", "precondition_invalidated", from_directive=True)
        if directive == "clarify":
            return self._decision(ctx, "clarify", "ask", "route_resolution_required", from_directive=True)
        if directive == "local_update":
            return self._decision(ctx, "local_update", "proceed", "latest_local_update_override", from_directive=True)
        if directive == "minimal_disclosure":
            return self._decision(ctx, "minimal_disclosure", "amend", "minimal_disclosure", from_directive=True)

        if explicit_local:
            return self._decision(ctx, "local_update", "proceed", "latest_local_update_override")

        if self._content_guard(ctx, focal, memory or {}):
            return self._decision(ctx, "guard", "hold", "precondition_invalidated")

        if self._must_guard(ctx):
            return self._decision(ctx, "guard", "hold", "precondition_invalidated")

        if self._needs_clarification(ctx, boundary, authority):
            return self._decision(ctx, "clarify", "ask", "route_resolution_required")

        if self._local_update_boundary(ctx, boundary, authority, route_snapshot):
            return self._decision(ctx, "local_update", "proceed", "local_update_boundary")

        if self._guardrail_raw_allowed(ctx, boundary, authority):
            return self._decision(ctx, "raw_dispatch", "proceed", "raw")

        if self._needs_minimal_disclosure(ctx, focal, boundary, route_snapshot):
            return self._decision(ctx, "minimal_disclosure", "amend", "minimal_disclosure")

        if self._summary_preferred(ctx, focal, target):
            return self._decision(ctx, "summary_dispatch", "proceed", "summary")

        if self._raw_allowed(ctx, focal):
            return self._decision(ctx, "raw_dispatch", "proceed", "raw")

        if "요약" in text or "summary" in text or focal.get("type") in {"file", "health_record"}:
            return self._decision(ctx, "summary_dispatch", "proceed", "summary")
        return self._decision(ctx, "raw_dispatch", "proceed", "inspect_context")

    def _decision(
        self,
        ctx: TaskContext,
        decision_class: str,
        control: str,
        reason: str,
        from_directive: bool = False,
    ) -> Decision:
        ctx.trace["decision_class"] = decision_class
        ctx.trace["decision_reason"] = reason
        ctx.trace["from_directive"] = from_directive
        return Decision(
            decision_class=decision_class, control=control, reason=reason, from_directive=from_directive
        )

    def _must_guard(self, ctx: TaskContext) -> bool:
        if "revok" in str(ctx.value("consent") or ""):
            return True
        if ctx.has_record("security_alert"):
            return True
        if ctx.has_record("safety_mode"):
            return True
        values = ctx.records_text.lower()
        guard_tokens = [
            "consent_revoked",
            "precondition_invalidated",
            "prior_success_invalidated",
            "fast_path_invalidation",
            "strict_policy_block",
            "phishing",
            "impersonation",
            "child_sleep_active",
            "raw_health_external_share",
        ]
        if any(token in values for token in guard_tokens):
            return True
        # Guard (hold) intent = the request's precondition is invalidated, so stop.
        # General stop/invalidation vocabulary (멈추다/중단/차단/보류/막다, 진행·실행
        # 하면 안, 전제가 사라지다/무효화/취소/깨지다).
        guard_phrases = [
            "진행하면 안",
            "진행하지 말",
            "실행하면 안",
            "실행을 막",
            "실행을 차단",
            "진행을 차단",
            "멈춰",
            "중단",
            "차단한다",
            "전제가 사라",
            "전제를 무효화",
            "허용 조건이 취소",
            "근거가 깨",
            "기대면 안",
        ]
        if any(phrase in ctx.all_text for phrase in guard_phrases):
            return True
        if (
            ctx.value("dispatch_authority_check") == "user_binding_pending"
            and dispatch_blocked(ctx.value("share_boundary_update"))
            and "외부 공유가 아니라" not in ctx.all_text
            and "상태만 갱신" not in ctx.all_text
            and "식별 가능한 세부값을 제외" not in ctx.all_text
            and "요약만 공유" not in ctx.all_text
        ):
            return True
        if (
            ctx.has_record("guardrail_ladder_signal")
            and ctx.value("dispatch_authority_check") == "authority_incomplete"
            and dispatch_blocked(ctx.value("share_boundary_update"))
            and "식별 가능한 세부값을 제외" not in ctx.all_text
            and "요약만 공유" not in ctx.all_text
            and "새 전제가 확정되지" not in ctx.all_text
        ):
            return True
        return False

    def _recalled_avoid(self, ctx: TaskContext, memory: dict[str, Any]) -> str | None:
        """The 'avoid' item stored in the recalled person's profile (allergy / forbidden
        preference), looked up from persistent memory by memory_key or person."""
        for value in ctx.values("persistent_memory_recall"):
            key = ""
            if isinstance(value, dict):
                key = str(value.get("memory_key") or value.get("person") or "")
                if value.get("avoid"):
                    return str(value["avoid"])
            elif isinstance(value, str):
                key = value
            profile = memory.get(key) if key else None
            if isinstance(profile, dict) and profile.get("avoid"):
                return str(profile["avoid"])
        return None

    def _content_guard(self, ctx: TaskContext, focal: dict[str, Any], memory: dict[str, Any]) -> bool:
        # A request that would send/act on an item the user's stored memory marks as
        # "avoid" (allergy / forbidden preference) is held — regardless of the item.
        avoid = self._recalled_avoid(ctx, memory)
        if avoid and avoid.lower() in ctx.prompt.lower():
            return True
        policy = str(ctx.value("external_share_policy") or "")
        if policy == "doctor_note_forbidden" and focal.get("type") == "health_record":
            if "새 전제가 확정되지" in ctx.all_text or "누구에게 어떤 범위" in ctx.all_text:
                return False
            return True
        return False

    def _needs_clarification(self, ctx: TaskContext, boundary: str, authority: str) -> bool:
        if "식별 가능한 세부값을 제외" in ctx.prompt or "요약만 공유" in ctx.prompt:
            return False
        if ctx.has_record("target_changed_after_turn"):
            return True
        if ctx.has_record("memory_conflict"):
            return True
        if ctx.has_record("payment_policy"):
            return True
        if ctx.has_record("amount_changed") or ctx.has_record("merchant_verification"):
            return True
        if (
            ctx.has_record("ambiguous_target")
            and is_redaction_directive(boundary)
            and authority == "internal_binding_confirmed"
            and not ctx.has_record("guardrail_ladder_signal")
        ):
            return True
        # A redaction boundary directive is an amend instruction (redact-and-dispatch);
        # the incomplete authority is resolved by redacting, not by asking. So the
        # authority/blocked catch-alls must not steal these tasks — they fall through
        # to minimal_disclosure. Genuine ambiguity below (explicit clarify phrases,
        # calendar_conflict, …) is still checked afterward.
        if not is_redaction_directive(boundary):
            if authority and not authority_confirmed(authority):
                return True
            if dispatch_blocked(boundary):
                return True
        if ctx.has_record("duration_ambiguous") and "확인" in ctx.all_text:
            return True
        if ctx.has_record("calendar_conflict"):
            return True
        # Ask (clarify) intent = confirm with the user before acting; the request is
        # not yet settled. General confirm/uncertainty vocabulary (확인/물어보다/질문,
        # 확정되지 않다/미확정/불분명/결론을 내릴 수 없다).
        clarify_phrases = [
            "먼저 확인",
            "다시 확인",
            "확인을 받",
            "확인 질문",
            "물어",
            "질문",
            "확정되지 않",
            "미확정",
            "불분명",
            "clarification",
            "결론을 내릴 수 없",
            "현재 정보만으로는 결론",
        ]
        if any(phrase in ctx.all_text for phrase in clarify_phrases):
            return True
        if (
            ctx.has_record("guardrail_ladder_signal")
            and is_local_boundary(boundary)
            and authority == "internal_binding_confirmed"
        ):
            return True
        return False

    def _guardrail_raw_allowed(self, ctx: TaskContext, boundary: str, authority: str) -> bool:
        return (
            ctx.has_record("guardrail_ladder_signal")
            and is_redaction_directive(boundary)
            and authority == "internal_binding_confirmed"
        )

    def _summary_preferred(self, ctx: TaskContext, focal: dict[str, Any], target: str) -> bool:
        if target == "legal_review" and any(token in ctx.all_text for token in ("요약", "점검", "공유 범위")):
            return True
        return False

    def _local_update_boundary(
        self, ctx: TaskContext, boundary: str, authority: str, route_snapshot: str
    ) -> bool:
        if is_local_boundary(boundary) and (authority_confirmed(authority) or authority == ""):
            return ctx.has_record("ambiguous_focal")
        if ctx.has_record("privacy_guard"):
            return True
        if ctx.has_record("trusted_subscription") and "refund" in str(ctx.value("payment_policy")).lower():
            return True
        if route_is_local_only(route_snapshot):
            return True
        return False

    def _needs_minimal_disclosure(
        self, ctx: TaskContext, focal: dict[str, Any], boundary: str, route_snapshot: str
    ) -> bool:
        if ctx.has_record("external_share_policy"):
            return True
        if ctx.has_record("enterprise_policy_recall"):
            return True
        if ctx.has_record("temporary_override_allowed"):
            return True
        if ctx.has_record("ops_memory_recall"):
            return True
        if ctx.has_record("persistent_memory_recall") and any(token in ctx.prompt for token in ("민감", "위치", "나이")):
            return True
        if is_redaction_directive(boundary):
            return True
        if is_local_boundary(boundary):
            return True
        if route_has_external(route_snapshot):
            return True
        if "strict" in str(ctx.value("session_share_policy") or ""):
            if is_external_channel(ctx.confirmed_channel()) and any(
                token in ctx.all_text for token in ("요약", "공유 범위", "점검", "민감")
            ):
                return True
        if self._sensitive_fields(focal) and "strict" in str(ctx.value("session_share_policy") or ""):
            if is_external_channel(ctx.confirmed_channel()) or ctx.has_record("ambiguous_focal"):
                return True
        return False

    def _raw_allowed(self, ctx: TaskContext, focal: dict[str, Any]) -> bool:
        attrs = focal.get("attrs") or {}
        contains = set(attrs.get("contains") or []) if isinstance(attrs.get("contains"), list) else set()
        if contains - {"summary", "title", "status"}:
            return False
        if "strict" in str(ctx.value("session_share_policy") or "") and ctx.has_record("ambiguous_target"):
            return False
        return focal.get("type") in {"message", "calendar_event", "file"}

    def _sensitive_fields(self, focal: dict[str, Any]) -> set[str]:
        attrs = focal.get("attrs") or {}
        contains = attrs.get("contains")
        if not isinstance(contains, list):
            return set()
        return {str(x) for x in contains if str(x) in SENSITIVE_FIELDS}


class ScopePolicyCompiler:
    def _minimal_excluded(self, focal: dict[str, Any], mode: str) -> list[str]:
        # Data-minimization (contextual-integrity): exclude a FIXED minimal set per mode,
        # not the full set of sensitive fields on the focal. Defaults are [raw_quote]
        # (redacted/summary) and [location, numeric_value, raw_quote] (status_only),
        # expanded only for identity documents (rrn → protect the name).
        attrs = focal.get("attrs") or {}
        contains = set(attrs.get("contains") or []) if isinstance(attrs.get("contains"), list) else set()
        if mode == "status_only":
            return ["location", "numeric_value", "raw_quote"]
        if mode == "summary":
            return ["name"] if "rrn" in contains else ["raw_quote"]
        if mode == "redacted":
            if "rrn" in contains:
                return ["name", "numeric_value", "raw_quote", "rrn"]
            if "location" in contains:
                return ["location", "numeric_value", "raw_quote"]
            return ["raw_quote"]
        return []

    def build_scope(self, ctx: TaskContext, focal: dict[str, Any], decision: Decision) -> dict[str, Any]:
        sensitive = self._excluded_fields(focal)
        if decision.decision_class == "guard":
            return {
                "mode": "none",
                "allowed_fields": [],
                "excluded_fields": [],
                "requires_user_confirmation": False,
            }
        if decision.decision_class == "clarify":
            # While pausing to confirm, the minimal disclosure is a summary (focal
            # sensitivity does not separate redacted from summary in the references).
            mode = "summary"
            if ctx.value("target_changed_after_turn") == "prior_success_route_superseded":
                mode = "none"
            return {
                "mode": mode,
                "allowed_fields": [] if mode == "none" else ["summary"],
                "excluded_fields": self._minimal_excluded(focal, mode) if mode != "none" else [],
                "requires_user_confirmation": True,
            }
        if decision.decision_class == "local_update":
            return {
                "mode": "status_only",
                "allowed_fields": ["status"],
                "excluded_fields": self._minimal_excluded(focal, "status_only"),
                "requires_user_confirmation": False,
            }
        if decision.decision_class == "minimal_disclosure":
            return {
                "mode": "redacted",
                "allowed_fields": ["summary"],
                "excluded_fields": self._minimal_excluded(focal, "redacted"),
                "requires_user_confirmation": ctx.has_record("ambiguous_target"),
            }
        if decision.decision_class == "summary_dispatch":
            # A plain summary dispatch already shares only a summary, so no explicit
            # field exclusion is needed on top of it.
            return {
                "mode": "summary",
                "allowed_fields": ["summary"],
                "excluded_fields": [],
                "requires_user_confirmation": False,
            }
        return {
            "mode": "raw",
            "allowed_fields": self._raw_allowed_fields(focal),
            "excluded_fields": [],
            "requires_user_confirmation": False,
        }

    def build_policy(
        self, ctx: TaskContext, focal: dict[str, Any], target: str, decision: Decision
    ) -> dict[str, Any]:
        flags: set[str] = set()
        violations: set[str] = set()
        sensitive = self._excluded_fields(focal)

        if "strict" in str(ctx.value("session_share_policy") or ""):
            flags.add("strict_share_policy")
        # An external share only when the operation's actual target is an external
        # channel. A directive-driven ask/hold resolves to the user, so a channel
        # confirmed elsewhere in the session does not by itself make this a share.
        if is_external_channel(target):
            flags.add("external_share")
        if (
            decision.decision_class == "local_update"
            or target == "memory_store"
            or is_local_boundary(ctx.value("share_boundary_update"))
        ):
            flags.add("local_only")
        if sensitive:
            flags.add("sensitive_content")
        if decision.decision_class == "minimal_disclosure":
            flags.add("minimal_disclosure")
        if ctx.has_record("ambiguous_target"):
            flags.add("target_ambiguity")
        if ctx.has_record("ambiguous_focal"):
            flags.add("ambiguous_focal")
        if decision.decision_class == "clarify":
            flags.add("clarification_required")
        if self._precondition_changed(ctx):
            flags.add("precondition_changed")
        if decision.decision_class == "guard":
            flags.update({"precondition_invalidated", "safety"})
            violations.add("precondition_changed_ignored")

        # Avoid over-penalizing update-only tasks that reference an external target in context.
        if decision.decision_class == "local_update" and target == "memory_store":
            flags.discard("external_share")

        return {
            "risk_flags": sorted(flags),
            "violations": sorted(violations),
            "requires_confirmation": decision.control == "ask" or self._soft_confirmation(ctx, decision),
        }

    def _precondition_changed(self, ctx: TaskContext) -> bool:
        # A precondition can change only once it was actually established: the request
        # runs through the route-binding pipeline AND its dispatch authority is
        # confirmed. While authority is still incomplete/pending (dispatch blocked),
        # nothing was bound yet, so there is no prior precondition to invalidate.
        # Authority is matched by the structural "confirmed" stem, not an enumerated list.
        return ctx.has_record("share_boundary_update") and str(
            ctx.value("dispatch_authority_check")
        ).endswith("_confirmed")

    def _soft_confirmation(self, ctx: TaskContext, decision: Decision) -> bool:
        if decision.control == "ask":
            return True
        # An amend with an ambiguous target still needs confirmation (mirrors the scope
        # field — both confirmation fields follow the same ambiguous-target signal).
        if decision.decision_class == "minimal_disclosure":
            return ctx.has_record("ambiguous_target")
        if decision.decision_class in {"raw_dispatch", "local_update"}:
            return ctx.has_record("ambiguous_target") and "strict" in str(ctx.value("session_share_policy") or "")
        return False

    def _excluded_fields(self, focal: dict[str, Any]) -> set[str]:
        attrs = focal.get("attrs") or {}
        values: list[Any] = []
        for key in ("contains", "fields"):
            raw = attrs.get(key)
            if isinstance(raw, list):
                values.extend(raw)
        normalized = {"numeric_value" if str(x) == "amount" else str(x) for x in values}
        return {value for value in normalized if value in SENSITIVE_FIELDS}

    def _strong_sensitive(self, focal: dict[str, Any]) -> bool:
        return bool(self._excluded_fields(focal) & {"rrn", "raw_quote", "numeric_value", "doctor_note", "card_number"})

    def _raw_allowed_fields(self, focal: dict[str, Any]) -> list[str]:
        # A raw dispatch discloses the item's summary and title (fixed per-mode allow set,
        # matching the other modes' fixed allow lists — redacted→summary, status_only→status).
        return ["summary", "title"]


class PlanCompiler:
    def build(
        self,
        ctx: TaskContext,
        focal_id: str,
        target: str,
        decision: Decision,
        scope: dict[str, Any],
        policy: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if decision.decision_class == "guard":
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "invalidated_precondition"}},
                {"verb": "guard", "target": focal_id, "args": {"reason": "precondition_invalidated"}},
            ]
        if decision.decision_class == "clarify":
            # The clarification's stated reason follows the policy layer: if a precondition
            # was flagged as changed, say so; otherwise it is an unresolved route/destination.
            # (Cross-layer consistency — the plan args match the policy flag, dev-validated.)
            if "precondition_changed" in set((policy or {}).get("risk_flags") or []):
                return [
                    {"verb": "read", "target": focal_id, "args": {"purpose": "clarify_precondition"}},
                    {"verb": "clarify", "target": "user", "args": {"reason": "precondition_changed"}},
                ]
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "route_resolution_required"}},
                {"verb": "clarify", "target": "user", "args": {"reason": "route_resolution_required"}},
            ]
        if decision.decision_class == "local_update":
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "local_update"}},
                {"verb": "verify", "target": "share_boundary_update", "args": {"scope": "local_update"}},
                {"verb": "update", "target": focal_id, "args": {"state": "local_status_only"}},
            ]
        if decision.decision_class == "minimal_disclosure":
            remove = "sensitive_fields" if len(scope.get("excluded_fields") or []) > 1 else (
                (scope.get("excluded_fields") or ["raw_quote"])[0]
            )
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "minimal_disclosure"}},
                {"verb": "redact", "target": focal_id, "args": {"remove": remove}},
                {"verb": "dispatch", "target": target, "args": {"scope": "redacted"}},
            ]
        if decision.decision_class == "summary_dispatch":
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "inspect_context"}},
                {"verb": "summarize", "target": focal_id, "args": {"mode": "summary"}},
                {"verb": "dispatch", "target": target, "args": {"scope": "summary"}},
            ]
        return [
            {"verb": "read", "target": focal_id, "args": {"purpose": "inspect_context"}},
            {"verb": "dispatch", "target": target, "args": {"scope": scope.get("mode", "raw")}},
        ]


class FinalHarness:
    def __init__(self) -> None:
        self.normalizer = TaskNormalizer()
        self.focal_resolver = FocalResolver()
        self.target_resolver = TargetResolver()
        self.decision_engine = DecisionEngine()
        self.scope_policy = ScopePolicyCompiler()
        self.plan_compiler = PlanCompiler()
        self.memory: dict[str, Any] = {}
        self.debug_traces: dict[str, dict[str, Any]] = {}

    def answer_task(self, task: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        # Fully self-contained: persistent memory is accumulated incrementally from each
        # task's own write records as the stream is processed (update_session_memory),
        # so a later recall reads a profile stored by an earlier task in the same run —
        # no look-ahead over the whole task list is performed.
        ctx = self.normalizer.normalize(task, session)
        self.update_session_memory(ctx)

        focal = self.focal_resolver.resolve(ctx)
        focal_id = str(focal.get("id") or "")
        preliminary_target = self.target_resolver.resolve(ctx, focal, memory=self.memory)
        decision = self.decision_engine.decide(ctx, focal, preliminary_target, memory=self.memory)
        target = self._final_target(ctx, focal, preliminary_target, decision)
        scope = self.scope_policy.build_scope(ctx, focal, decision)
        policy = self.scope_policy.build_policy(ctx, focal, target, decision)
        plan_events = self.plan_compiler.build(ctx, focal_id, target, decision, scope, policy)

        session["last_focal_id"] = focal_id
        session["last_target"] = target
        session["last_control"] = decision.control
        session["last_decision_class"] = decision.decision_class
        self.debug_traces[str(task.get("id"))] = dict(ctx.trace)

        return {
            "focal_id": focal_id,
            "target": target,
            "control": decision.control,
            "content_scope": scope,
            "policy": policy,
            "plan_events": plan_events,
            "user_response": self.user_response(decision, target, scope),
            "audit_tags": self.audit_tags(ctx, decision),
            "counterfactual": "최신 target, 동의, 보안 신호, 공유 경계가 달라지면 판단이 달라질 수 있습니다.",
        }

    def update_session_memory(self, ctx: TaskContext) -> None:
        for value in ctx.values("persistent_memory_write"):
            if isinstance(value, dict):
                key = str(value.get("memory_key") or value.get("person") or "")
                if key:
                    self.memory[key] = value
        ctx.session["last_record_set"] = ctx.trace.get("record_set")

    def _final_target(
        self, ctx: TaskContext, focal: dict[str, Any], preliminary_target: str, decision: Decision
    ) -> str:
        # Target follows the DECISION PROVENANCE:
        #  - A "keep local" decision (explicit local directive or a memory-write record)
        #    writes to internal memory → memory_store; a local update forced only by a
        #    boundary/route signal still dispatches to its resolved channel.
        #  - A directive-driven ask/hold is the user asking to confirm / stop, so it
        #    responds to the user; a record-driven ask/hold is holding the channel the
        #    operation was headed to, so the channel stays the target.
        if decision.decision_class == "local_update":
            if decision.from_directive or self.target_resolver._explicit_memory_store(ctx):
                return "memory_store"
            return preliminary_target
        if ctx.has_record("persistent_memory_write"):
            return "memory_store"
        changed = ctx.value("target_changed_after_turn")
        if isinstance(changed, str) and changed and not changed.startswith("prior_"):
            return changed
        if decision.control in ("ask", "hold") and decision.from_directive:
            return "user"
        return preliminary_target

    def audit_tags(self, ctx: TaskContext, decision: Decision) -> list[str]:
        tags = [decision.decision_class]
        if ctx.trace.get("resolver_source"):
            tags.append(str(ctx.trace["resolver_source"]))
        if ctx.has_record("focal_marker_refs"):
            tags.append("marker_trace")
        return sorted(set(tags))

    def user_response(self, decision: Decision, target: str, scope: dict[str, Any]) -> str:
        # A short, concrete description of the action taken, naming the operative
        # destination, disclosure scope, and any excluded fields where relevant.
        mode = scope.get("mode", "summary")
        excluded = scope.get("excluded_fields") or []
        excl_txt = ", ".join(excluded)
        if decision.control == "hold":
            return "최신 안전·동의·전제 신호를 확인한 결과 처리 전제가 유효하지 않아, 이 요청은 보류하고 진행하지 않겠습니다."
        if decision.control == "ask":
            return "대상과 공유 범위가 아직 확정되지 않아, 실행 전에 어떤 대상에게 어느 범위로 처리할지 먼저 확인하겠습니다."
        if decision.decision_class == "local_update" or target == "memory_store":
            return "외부로 전달하지 않고 기기 내부 상태만 갱신하겠습니다."
        if decision.control == "amend":
            if excl_txt:
                return f"{excl_txt} 항목은 제외하고 요약 수준으로 {target}에 공유하겠습니다."
            return f"식별 가능한 원문·민감 세부 정보는 제외하고 요약 수준으로 {target}에 공유하겠습니다."
        if mode == "raw":
            return f"요청한 내용을 원문 그대로 {target}에 처리하겠습니다."
        if excl_txt:
            return f"{excl_txt} 항목을 제외한 {mode} 범위로 {target}에 처리하겠습니다."
        return f"필요한 범위를 {mode}(으)로 정리해서 {target}에 처리하겠습니다."


def participant_task_view(task: dict[str, Any]) -> dict[str, Any]:
    view = json.loads(json.dumps(task, ensure_ascii=False))
    for key in list(view):
        if (
            key in {"expected_events", "answer"}
            or key.startswith("expected_")
            or key.endswith("_brief")
            or key.endswith("_notes")
            or key.endswith("_rubric")
            or key.endswith("_keywords")
            or key.endswith("_tags")
        ):
            view.pop(key, None)
    return view


def answer_one(harness: Any, task: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    for name in ("answer_task", "solve_task", "solve"):
        fn = getattr(harness, name, None)
        if callable(fn):
            answer = fn(task, session)
            if not isinstance(answer, dict):
                raise RuntimeError(f"{name} returned non-object for task {task.get('id')}")
            return answer
    raise RuntimeError("harness must expose answer_task(task, session), solve_task(...), or solve(...)")


def run_harness(
    tasks: list[dict[str, Any]],
    harness_cls: type = FinalHarness,
    *,
    harness_name: str = "scpc_deterministic_harness",
    return_harness: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], Any]:
    ordered = sorted(
        tasks,
        key=lambda t: (str(t.get("session_id", "")), int(t.get("turn_index", 0)), str(t.get("id", ""))),
    )
    harness = harness_cls()
    sessions: dict[str, dict[str, Any]] = {}
    answers: dict[str, dict[str, Any]] = {}
    for task in ordered:
        sid = str(task.get("session_id", ""))
        session = sessions.setdefault(sid, {})
        answers[str(task["id"])] = answer_one(harness, participant_task_view(task), session)

    payload = {
        "schema": SUBMISSION_SCHEMA,
        "meta": {
            "harness_name": harness_name,
            "uses_external_api": False,
            "fixed_slm_policy": "local_fixed_slm_only",
            "model_id": FIXED_SLM_ID,
            "temperature": 0.0,
            "seed": 2026,
        },
        "answers": answers,
    }
    if return_harness:
        return payload, harness
    return payload


def validate_payload(payload: dict[str, Any], expected_ids: set[str] | None = None) -> None:
    if payload.get("schema") != SUBMISSION_SCHEMA:
        raise ValueError(f"schema must be {SUBMISSION_SCHEMA}")
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("meta is required")
    if meta.get("fixed_slm_policy") != "local_fixed_slm_only":
        raise ValueError("meta.fixed_slm_policy must be local_fixed_slm_only")
    if meta.get("uses_external_api") is not False:
        raise ValueError("meta.uses_external_api must be false")
    if meta.get("model_id") != FIXED_SLM_ID:
        raise ValueError(f"meta.model_id must be {FIXED_SLM_ID}")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    if expected_ids is not None:
        missing = sorted(expected_ids - set(answers))
        extra = sorted(set(answers) - expected_ids)
        if missing:
            raise ValueError(f"missing answers: {missing[:5]} ... total={len(missing)}")
        if extra:
            raise ValueError(f"extra answers: {extra[:5]} ... total={len(extra)}")
    for task_id, answer in answers.items():
        if not isinstance(answer, dict):
            raise ValueError(f"answer for {task_id} must be an object")
        for field_name in ["focal_id", "target", "control", "content_scope", "policy", "plan_events"]:
            if field_name not in answer:
                raise ValueError(f"answer for {task_id} missing {field_name}")
        if answer["control"] not in VALID_CONTROLS:
            raise ValueError(f"invalid control for {task_id}: {answer['control']}")
        scope = answer.get("content_scope")
        if not isinstance(scope, dict) or scope.get("mode") not in VALID_SCOPE_MODES:
            raise ValueError(f"invalid content_scope for {task_id}")
        if not isinstance(answer.get("policy"), dict):
            raise ValueError(f"invalid policy for {task_id}")
        if not isinstance(answer.get("plan_events"), list):
            raise ValueError(f"invalid plan_events for {task_id}")

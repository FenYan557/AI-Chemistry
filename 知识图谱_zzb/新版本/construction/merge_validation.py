"""合并提案的统一验收门禁：document 与 cross 阶段共用。

许可的必要条件（缺一不可）：
1. 提案显式 decision == "merge"；keep_separate / uncertain 永不 union。
2. 提案带逐字同一性证据（source_id + quote 形式，可多组），且 quote 逐字出现在
   对应成员的输入 contexts 中，source_id 也必须对应。
3. 现有 incompatible 规则（不同方法、氧化还原态/盐型/水合冲突、种类冲突等）
   作为额外拒绝检查继续生效。

关键词只用于额外拒绝（理由与成员矛盾、含拒绝/不确定/自纠正措辞），
绝不作为合并许可依据。历史无证据提案一律拒收为待审，不静默 merge。
"""

import sys as _construction_sys
from pathlib import Path as _ConstructionPath
_construction_sys.path.insert(0, str(_ConstructionPath(__file__).resolve().parents[1] / "scripts"))
_construction_sys.path.insert(0, str(_ConstructionPath(__file__).resolve().parent))
import re
from collections import defaultdict

DECISIONS = ("merge", "keep_separate", "uncertain")

# 理由与成员名单矛盾 / 自纠正的典型措辞：仅作拒绝信号，不作许可信号
_CONTRADICTION_RE = re.compile(
    r"do not merge|don't merge|not the same|different (chemical|species|method|compound|sample)|"
    r"keep (them )?separate|should not (be )?merged|cannot (be )?merge|must not merge|"
    r"wait,|but n0|however.*separate|不确定|不是同一|不合并|分开|待核", re.I)


def _context_quote(rows_by_id, ids, source_id, quote):
    """验证 (source_id, quote) 是否逐字出现在至少一个成员的输入 contexts 中。
    返回 (是否通过, 命中的成员id或None)。"""
    if not isinstance(quote, str) or not quote.strip() or not isinstance(source_id, str) or not source_id.strip():
        return False, None
    for rid in ids:
        row = rows_by_id.get(rid)
        if not row:
            continue
        for context in row.get("contexts", []):
            if context.get("source_id") == source_id and quote in context.get("text", ""):
                return True, rid
    return False, None


def _identity_evidence_ok(rows_by_id, ids, proposal):
    """同一性证据：evidence 数组，每项含 source_id/quote 且逐字对应输入 contexts。"""
    evidence = proposal.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False, "缺少同一性证据(source_id+quote)"
    hits = 0
    for item in evidence:
        if not isinstance(item, dict):
            return False, "证据项不是对象"
        ok, _ = _context_quote(rows_by_id, ids, item.get("source_id"), item.get("quote"))
        if not ok:
            return False, "证据quote/source_id与输入contexts不对应: %r" % (item,)
        hits += 1
    return True, None


def gate_proposal(proposal, rows_by_id, ids, incompatible_reason=None, phase=None):
    """单条提案验收。

    返回 (accepted, rejection_reason)。
    - accepted=False 且 rejection_reason=None 表示 keep_separate/uncertain：安静不合并（仍记录为 not_merged）。
    - accepted=False 且 rejection_reason=字符串：拒收为待审。
    """
    if not isinstance(proposal, dict):
        return False, "提案不是对象"
    ids = sorted(set(ids))
    if not set(ids) <= set(rows_by_id):
        return False, "合并含未知ID: %s" % sorted(set(ids) - set(rows_by_id))
    decision = proposal.get("decision")
    if decision not in DECISIONS:
        # 旧式 same_as 提案（只有 ids+reason，无 decision 无证据）：不得默默 merge
        return False, "缺少显式decision，旧式无证据提案拒收为待审"
    if decision in ("keep_separate", "uncertain"):
        return False, None
    ok, why = _identity_evidence_ok(rows_by_id, ids, proposal)
    if not ok:
        return False, why
    # 额外拒绝检查：理由与成员矛盾/含拒绝或自纠正措辞
    reason = proposal.get("reason") or ""
    labels = " | ".join(str(rows_by_id[i].get("canonical_label") or rows_by_id[i].get("label") or i) for i in ids)
    if _CONTRADICTION_RE.search(reason):
        return False, "理由含拒绝/不确定/自纠正措辞，与decision=merge矛盾，拒收为待审"
    if labels and _reason_contradicts_members(reason, labels, ids):
        return False, "理由与成员名单矛盾，拒收为待审"
    # 原有 incompatible 约束继续生效（不同方法、价态/盐型/水合/规格冲突、种类冲突等）
    if incompatible_reason:
        return False, incompatible_reason
    if phase == "document":
        docs = {rows_by_id[i].get("document_id") for i in ids}
        if len(docs) != 1:
            return False, "document merge crosses documents"
    return True, None


def _reason_contradicts_members(reason, labels, ids):
    """理由明确把成员说成"不同物质/不合并"时与 decision=merge 矛盾。

    只捕捉显式拒绝信号（不依赖成员名是否出现在理由里，避免被改写绕过）。
    """
    lowered = reason.casefold()
    if re.search(r"these are different|是不同|不同化学|different chemicals|distinct chemical", lowered):
        return True
    if labels and re.search(r"do not merge|don't merge|not the same|keep (them )?separate|"
                            r"should not (be )?merged|cannot (be )?merge|must not merge|不合并|不是同一", lowered):
        if any(lbl.casefold() in lowered for lbl in str(labels).split(" | ") if lbl):
            return True
    return False


def apply_gated_merges(rows, proposals, phase, incompatible_fn):
    """带门禁的合并执行：替代旧 apply_merges 的入口语义。

    返回 (groups, accepted, rejected, not_merged)。
    - accepted: 通过门禁并执行 union 的提案
    - rejected: 拒收为待审（带 rejection 原因）
    - not_merged: keep_separate/uncertain，安静保留独立
    """
    from resolve_entities_llm import Union  # 同一 Union 实现，避免漂移

    indexed = {r["id"]: r for r in rows}
    union = Union(indexed)
    members = {i: {i} for i in indexed}
    accepted, rejected, not_merged = [], [], []
    for proposal in proposals:
        ids = sorted(set(proposal.get("ids", [])))
        roots = {union.find(i) for i in ids if i in indexed}
        all_ids = set().union(*(members[root] for root in roots)) if roots else set(ids)
        group = [indexed[i] for i in all_ids] if all_ids else []
        incompatible_reason = incompatible_fn(group) if group else None
        ok, why = gate_proposal(proposal, indexed, ids,
                                incompatible_reason=incompatible_reason, phase=phase)
        if ok:
            for item in ids[1:]:
                union.join(ids[0], item)
            root = union.find(ids[0])
            members[root] = all_ids
            for old in roots - {root}:
                members.pop(old, None)
            accepted.append(proposal)
        elif why is None:
            not_merged.append(proposal)
        else:
            rejected.append({**proposal, "rejection": why})
    groups = defaultdict(list)
    for row in rows:
        groups[union.find(row["id"])].append(row)
    return list(groups.values()), accepted, rejected, not_merged


# PARENT_IDENTITY_PROOF_V2
# An unrelated literal quote is not identity evidence. Each member must be covered,
# and source_definition must connect the actual names rather than merely list them.
_original_evidence_check = _identity_evidence_ok
def _compact(value):
    import unicodedata
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or ""))

def _source_names(row):
    choices = set()
    for label in [row.get("label") or row.get("canonical_label") or ""]:
        if not label:
            continue
        choices.add(_compact(label))
        choices.add(_compact(re.sub(r"\s*\([A-Za-z0-9_-]{1,12}\)\s*$", "", label)))
    return {v for v in choices if v}

def _identity_evidence_ok(rows_by_id, ids, proposal):
    ok, why = _original_evidence_check(rows_by_id, ids, proposal)
    if not ok:
        return ok, why
    basis = proposal.get("basis")
    if basis not in {"source_definition", "format_equivalence"}:
        return False, "identity basis must be source_definition or format_equivalence"
    covered = set()
    for evidence in proposal["evidence"]:
        for rid in ids:
            row = rows_by_id[rid]
            for context in row.get("contexts", []):
                if context.get("source_id") == evidence["source_id"] and evidence["quote"] in context.get("text", ""):
                    if any(n in _compact(evidence["quote"]) for n in _source_names(row)):
                        covered.add(rid)
    if set(ids) != covered:
        return False, "identity evidence does not cover every member name"
    raw_labels = [_compact(rows_by_id[i].get("label") or rows_by_id[i].get("canonical_label")) for i in ids]
    cross = proposal.get("_identity_phase") == "cross" or len({rows_by_id[i].get("document_id") for i in ids}) > 1
    if basis == "format_equivalence":
        if len(set(raw_labels)) != 1:
            return False, "format_equivalence cannot rename different labels"
        if cross and re.fullmatch(r"[A-Z0-9_-]{1,8}", raw_labels[0]):
            return False, "unknown acronym alone cannot establish cross-document identity"
        return True, None
    if cross:
        for rid, raw in zip(ids, raw_labels):
            if not re.fullmatch(r"[A-Z0-9_-]{1,8}", raw):
                continue
            expanded = {name for other in ids if other != rid for name in _source_names(rows_by_id[other]) if not re.fullmatch(r"[A-Z0-9_-]{1,8}", name)}
            own_definition = any(e["source_id"] == c.get("source_id") and e["quote"] in c.get("text", "") and any(name + "(" + raw + ")" in _compact(e["quote"]) or raw + "standsfor" + name in _compact(e["quote"]) for name in expanded) for e in proposal["evidence"] for c in rows_by_id[rid].get("contexts", []))
            if not own_definition:
                return False, "each cross-document acronym needs its own source definition of the same full name"
    parent = {i: i for i in ids}
    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for left in ids:
        for right in ids:
            if left >= right:
                continue
            connected = False
            for evidence in proposal["evidence"]:
                quote = _compact(evidence["quote"])
                for a in _source_names(rows_by_id[left]):
                    for b in _source_names(rows_by_id[right]):
                        if a == b:
                            if not (cross and re.fullmatch(r"[A-Z0-9_-]{1,8}", a)):
                                connected = True
                        elif a + "(" + b + ")" in quote or b + "(" + a + ")" in quote:
                            connected = True
                        else:
                            for x, y in [(a, b), (b, a)]:
                                if re.search(re.escape(x) + r"(?:isalsoknownas|isknownas|standsfor|isabbreviatedas|iscalled|isdenotedby|简称|称为|记为)" + re.escape(y), quote):
                                    connected = True
            if connected:
                parent[find(left)] = find(right)
    if len({find(i) for i in ids}) != 1:
        return False, "source quotes do not establish a connected same-identity definition for member names"
    return True, None

_original_gate = gate_proposal
def gate_proposal(proposal, rows_by_id, ids, incompatible_reason=None, phase=None):
    if not isinstance(proposal, dict) or len(set(ids)) < 2:
        return False, "merge proposal must contain at least two distinct member IDs"
    if not isinstance(proposal.get("reason"), str) or not proposal["reason"].strip():
        return False, "merge reason is required"
    if proposal.get("decision") == "merge" and _CONTRADICTION_RE.search(proposal["reason"]):
        return False, "理由含拒绝或矛盾措辞，拒收为待审"
    return _original_gate({**proposal, "_identity_phase": phase}, rows_by_id, ids, incompatible_reason, phase)

def apply_gated_merges(rows, proposals, phase, incompatible_fn):
    from resolve_entities_llm import Union
    indexed = {r["id"]: r for r in rows}
    union = Union(indexed)
    members = {i: {i} for i in indexed}
    accepted, rejected, not_merged = [], [], []
    forbidden = set()
    for proposal in proposals:
        if proposal.get("decision") in {"keep_separate", "uncertain"}:
            ids = [i for i in proposal.get("ids", []) if i in indexed]
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    forbidden.add(frozenset((a, b)))
    for proposal in proposals:
        ids = sorted(set(proposal.get("ids", [])))
        roots = {union.find(i) for i in ids if i in indexed}
        all_ids = set().union(*(members[root] for root in roots)) if roots else set(ids)
        group = [indexed[i] for i in all_ids if i in indexed]
        incompatible = incompatible_fn(group) if group else None
        if any(pair <= all_ids for pair in forbidden):
            incompatible = "merge would violate explicit keep_separate/uncertain constraint transitively"
        ok, why = gate_proposal(proposal, indexed, ids, incompatible, phase)
        if ok:
            for item in ids[1:]:
                union.join(ids[0], item)
            root = union.find(ids[0])
            members[root] = all_ids
            for old in roots - {root}:
                members.pop(old, None)
            accepted.append(proposal)
        elif why is None:
            not_merged.append(proposal)
        else:
            rejected.append({**proposal, "rejection": why})
    groups = defaultdict(list)
    for row in rows:
        groups[union.find(row["id"])].append(row)
    return list(groups.values()), accepted, rejected, not_merged

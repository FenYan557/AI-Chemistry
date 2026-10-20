"""基于真实示例的表达/接口核查；不等于语义准确率或全库覆盖率。"""
import copy
import json
from pathlib import Path
from validate import validate, load
from materialize import materialize, retrieval_keys
from answer_context import build_context

ROOT = Path(__file__).resolve().parents[1]


def review():
    base = load(ROOT / "examples/literature_bundle.json")
    hard = load(ROOT / "examples/hard_cases.json")

    def blocked(change):
        data = copy.deepcopy(hard)
        change(data)
        return {e["code"] for e in validate(data)["errors"]}

    def reverse(data):
        edge = next(e for e in data["edges"] if e["fact_id"] == "h:adsorption")
        edge["from_entity_id"], edge["to_entity_id"] = edge["to_entity_id"], edge["from_entity_id"]

    def forge(data):
        fact = next(f for f in data["facts"] if f["id"] == "h:annealed_resistivity")
        fact["outcomes"][0]["comparison"]["baseline_raw"] = "99999 invented baseline"

    reordered = copy.deepcopy(hard)
    for fact in reordered["facts"]:
        fact["participants"].reverse()
    ctx = build_context(base)
    checks = {
        "两个真实片段映射示例结构合法": validate(base)["valid"] and validate(hard)["valid"],
        "调换边端点被拒绝": "EDGE_DERIVATION_MISMATCH" in blocked(reverse),
        "编造比较基准被拒绝": "COMPARISON_BASELINE_NOT_LITERAL" in blocked(forge),
        "参与者换序不改变边": materialize(reordered)["edges"] == hard["edges"],
        "开放事实保留事实级检索": len(retrieval_keys(hard)["fact_keys"]) == len(hard["facts"]),
        "默认回答上下文不输出审核报告": "audit" not in ctx and all("review" not in f for f in ctx["evidence"]),
        "观测解释展望分别可表达": {"observation", "author_interpretation", "future_work"} <= {f["statement_type"] for f in base["facts"]},
    }
    return {"schema_version": "4.0.0-draft", "scope": "3篇4块人工映射与接口回归，不是全库或抽取金标",
            "checks": checks, "all_observed_checks_passed": all(checks.values()),
            "not_verified": ["全库抽取准确率", "化学语义正确率", "最终接入模型能力", "独立隔离的三路问答收益"],
            "deferred": ["化学身份全局消歧", "单位换算平台", "自动冲突裁决", "全库抽取"]}


if __name__ == "__main__":
    report = review()
    (ROOT / "reports/protocol_review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["all_observed_checks_passed"] else 1)

"""生成固定证据范围的四场景三路输入；不调用模型，不预制标准答案。"""
import json
from pathlib import Path
from answer_context import build_context, ANSWER_INSTRUCTION

ROOT = Path(__file__).resolve().parents[1]


def build():
    bundle = json.loads((ROOT / "examples/literature_bundle.json").read_text(encoding="utf-8"))
    scenarios = [
        ("concentration", "根据现有信息，ADO的作用是否与浓度有关？如何理解其加速与抑制机制？", ["f:ado:low", "f:ado:high", "f:ado:interpretation"]),
        ("numeric", "该糖精研究中，退火前后电阻率怎样变化？计算降幅，并说明能否全部归因于糖精。", ["f:resistivity:reported", "f:resistivity:annealed"]),
        ("future", "NA与其他浆料组分的协同效应已经得到验证了吗？对下一步候选验证有什么启示？", ["f:cmp:future"]),
        ("analogy", "除文献已出现的添加剂外，能否提出一类值得进一步筛选的候选及机理理由？不要把类比当成已验证效果。", ["f:ado:interpretation", "f:cmp:future"]),
    ]
    facts = {f["id"]: f for f in bundle["facts"]}
    inputs = []
    for case, question, ids in scenarios:
        docs = {facts[i]["document_id"] for i in ids}
        blocks = [b for b in bundle["blocks"] if b["document_id"] in docs]
        raw = [{"citation": b["id"], "document": b["document_id"], "text": b["text"]} for b in blocks]
        structured = build_context(bundle, ids)
        # 两个检索臂提供同一范围原文，结构臂只多给其派生的事实视图。
        for arm, data in [("model_only", None), ("raw", raw), ("structured", {"raw_sources": raw, "facts": structured["evidence"]})]:
            inputs.append({"case": case, "arm": arm, "question": question, "context": data})
    return inputs


if __name__ == "__main__":
    data = build()
    (ROOT / "examples/probe_inputs.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = ("你执行一次有界回答测试。不要调用任何工具、不要读写文件、不要委派。仅返回最终JSON数组，12项，每项为case/arm/answer。"
            "分别独立回答每一项，只可使用该项context和你的背景知识，不能借用其他项证据；每项中文不超过100字。"
            "这是一次批量烟雾测试，不能保证不同项完全隔离。\n" + ANSWER_INSTRUCTION +
            "\n输入:\n" + json.dumps(data, ensure_ascii=False))
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-output", type=Path, required=True)
    args = parser.parse_args()
    args.prompt_output.write_text(text, encoding="utf-8")
    print(json.dumps({"cases": 4, "arms": 3, "prompt_chars": len(text)}, ensure_ascii=False))

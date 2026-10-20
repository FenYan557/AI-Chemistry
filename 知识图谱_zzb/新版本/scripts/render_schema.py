"""从机器契约与登记表生成可读 schema，按九项（实体/签名/标识/属性/词表/约束/上下文/溯源/治理）
加消费端契约与标准映射组织。字段说明为人工注解，其余内容一律来自 JSON 文件。

改契约或登记表后重新渲染，不要手改 schema/schema.md。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


FIELD_NOTE = {
    "id": "记录唯一标识",
    "document_id": "所属文献；跨文献引用视为错误",
    "title": "文献标题",
    "source_file": "清洗产物中的块文件路径",
    "sha256": "来源文件哈希，用于追溯快照",
    "source_kind": "来源类型：cleaned_text / original_pdf / other",
    "page": "页码；未知时为 null 并告警",
    "section": "章节标题原文",
    "text": "块正文，引用必须逐字取自这里",
    "surface": "原文提及的字面写法",
    "candidate_type_ids": "候选类型编号；未登记类型只进候选",
    "evidence": "证据：块内偏移或表格单元格",
    "canonical_label": "规范名称（篇内或全局）",
    "scope": "身份作用域：document（篇内）或 global（跨篇）",
    "status": "状态取值（含义随所在对象而定，见受控词表）",
    "external_refs": "关联的外部记录编号",
    "distinctions": "电荷/盐型/水合物/立体化学/规格等不可合并差别",
    "mention_id": "指向的原文提及",
    "identity_id": "已核身份；pending 合并不写入",
    "from_identity_id": "合并/拆分记录的起点身份",
    "to_identity_id": "合并/拆分记录的终点身份",
    "relation": "关系：原始表达＋定义＋候选编号",
    "rationale": "合并或拒并的理由（必填，供审计）",
    "basis": "依据：作者明确/结构/数据库/仅名称候选",
    "review": "后台人工审核状态；pending不自动禁止引用/分析",
    "external_ref": "引用的外部记录",
    "resource": "外部资源名（pubchem/chebi 等）",
    "resource_id": "外部资源标识",
    "retrieved_at": "查询时间",
    "response_sha256": "缓存响应哈希",
    "cache_file": "缓存文件位置",
    "match_status": "外部匹配状态",
    "identity_basis": "匹配依据说明",
    "group_id": "同一研究的记录分组；不能代替 Run",
    "participants": "参与者：提及＋语义角色",
    "conditions": "条件；可标记从 Run 继承",
    "outcomes": "结果；可绑定样品",
    "cited_work": "转述对象：原文指称＋可解析到的文献；未转述时三字段均为 null",
    "statement_type": "陈述性质：观察/计算/作者解释/未来工作/转述/未知",
    "source_scope": "来源范围：本研究/引用他人/综述归纳/未知",
    "polarity": "肯定/否定/无效应/未知",
    "modality": "语气：明确/保留/推测/未知",
    "run_id": "所属 Run；继承条件时必填",
    "extraction": "抽取方法、模型与协议版本",
    "notes": "人工备注，不参与校验",
    "parameter_raw": "条件参数的原文写法",
    "candidate_parameter": "候选参数编号；未登记只作候选",
    "value": "数值或定性取值对象",
    "value_raw": "原始取值文本；数值型须逐字出现在证据中",
    "value_kind": "取值形态：数值/定性/序数/缺失",
    "unit_raw": "原始单位文本",
    "unit_status": "单位状态：已报告/未报告/不适用/未解析",
    "indicator_raw": "指标原文",
    "direction": "变化方向；unknown 表示原文未给方向",
    "stage_raw": "处理阶段原文（如退火后）",
    "magnitude": "程度限定：原措辞＋slight/moderate/marked/unknown",
    "qualifier": "程度档：slight / moderate / marked / unknown",
    "raw": "原文表达",
    "comparison": "比较基准：状态＋基准值/基准提及/基准口径",
    "baseline_raw": "基准值原文（如退火前的 14.4 μΩ·cm）",
    "baseline_mention_id": "基准提及；须为本事实参与者",
    "basis_raw": "基准口径原文（未给出时为 null）",
    "sample_id": "结果所属样品",
    "functional_role": "功能角色（受控多选之一）",
    "role_raw": "原文角色措辞；other 与 author_explicit 必填",
    "role_basis": "角色依据：作者明确/效果推测/未知",
    "fact_id": "所属事实",
    "subject_mention_id": "角色归属的物质提及",
    "note": "单条记录备注",
    "label": "原文标签或简述",
    "shared_note": "系列共享条件说明（自由文本，不参与求交）",
    "experiment_id": "所属实验系列",
    "material_raw": "材料原文",
    "form_raw": "形态原文（膜/粉/基底）",
    "state_raw": "状态原文（镀态/退火态）",
    "treatment_raw": "处理原文",
    "derived_from_sample_id": "来源样品，用于表达处理前后",
    "start": "引用起始偏移（含）",
    "end": "引用结束偏移（不含）",
    "quote": "逐字引文；必须等于块内对应片段",
    "kind": "证据类型：block 或 table_cell",
    "table_id": "表格标识，须以 doc_id 开头",
    "row": "表格行号（0 起，表头计入）",
    "col": "表格列号（0 起）",
    "cell_raw": "单元格原文；必须与该 CSV 单元格完全一致",
    "inherited": "条件是否来自 Run 继承",
    "about_mention_ids": "条件作用对象",
    "scope_status": "条件作用范围是否已明确",
    "candidate_relation_id": "候选关系编号；未登记只作候选",
    "definition": "关系定义",
    "method": "抽取方式",
    "model": "模型标识；规则映射为 null",
    "protocol_version": "协议版本",
    "type_id": "实体类型；null 表示未定类型，会触发 audit 提示",
    "from_mention_id": "实体来源提及",
    "from_entity_id": "边起点实体",
    "to_entity_id": "边终点实体",
    "qualifiers": "边的限定：陈述性质/来源范围/极性/模态/条件，全部复制自事实",
    "reference_raw": "被引文献的原文指称",
    "semantics_verified": "语义是否已人工验证（本协议恒为 false）",
}

FIELD_NOTE_BY_DEF = {
    ("comparison", "status"): "比较基准状态：not_stated（未给）/ raw_only（只有文字）/ explicit（有数值）",
    ("identity", "status"): "身份核验状态：unresolved / candidate / reviewed",
    ("identity_link", "identity_id"): "指向的规范身份",
    ("identity_merge", "relation"): "同一性操作：same_as（合并）或 distinct_from（拆分/拒并）",
    ("identity_merge", "status"): "持久化状态",
    ("magnitude", "raw"): "程度原措辞；qualifier 非 unknown 时必填",
}

BUNDLE_NOTE = {
    "documents": "L0 文献",
    "blocks": "L0 文本块（表格/图/公式以此定位）",
    "mentions": "L3 原文提及（保留表面串）",
    "identities": "L3 规范身份（篇内或跨篇）",
    "identity_links": "L3 提及→身份映射及其依据",
    "identity_merges": "L3 身份合并/拆分/拒并记录",
    "external_records": "外部资源查询缓存记录",
    "facts": "L2/L4 事实（事件实体：参与者＋条件＋结果＋陈述性质）",
    "experiments": "L2 实验系列",
    "runs": "L2 一次条件组合",
    "samples": "L3 样品与处理前后状态",
    "role_assignments": "L2 功能角色选择（受控多选）",
    "entities": "物化层实体（由 mention 派生，id=ent:<mention_id>）",
    "edges": "物化层边（由事实派生，边不新增语义）",
}

NESTED_DEFS = ["evidence", "quantity", "relation_ref", "magnitude", "comparison",
               "condition", "outcome", "quantity_condition", "entity", "edge", "identity_merge"]

NINE = [
    ("1", "实体类型（节点类）", "registry/entity_types.json", "判据/正例/反例/边界；无判据不可实例化"),
    ("2", "关系定义域与值域（签名）", "registry/relations.json", "域/值域/方向/基数；core 才可实例化"),
    ("3", "标识与唯一性", "registry/identity_rules.json + identity_merges", "ID 规则、合并/拆分/拒并留痕"),
    ("4", "属性表示边界", "registry/vocab.json representation_policy", "何时升节点、何时留属性"),
    ("5", "受控词表与枚举", "registry/vocab.json + roles.json", "封闭取值、层级、别名、候选晋升"),
    ("6", "约束与处置", "schema/constraints.json", "block/review/warn 三档 × 执行点"),
    ("7", "上下文与 n-ary", "facts(事件) + edges(限定边) + magnitude/comparison", "条件挂事实，基准显式"),
    ("8", "溯源与可信度", "facts 的陈述性质/证据/抽取 + cited_work", "未报告与不确定显式表达"),
    ("9", "演化与治理", "budget + promotion + 迁移规则", "预算上限、晋升流程、命名与审计"),
    ("补", "消费端契约", "registry/consumer_contract.json", "事实级检索与按用途判断"),
    ("补", "复用成熟标准", "registry/standards_mapping.json", "PROV-O/SOSA/QUDT/ChEBI 字段映射"),
]


def note_for(name, def_name=None):
    return FIELD_NOTE_BY_DEF.get((def_name, name)) or FIELD_NOTE.get(name, "")


def type_text(spec):
    if "$ref" in spec:
        return "→ " + spec["$ref"].split("/")[-1]
    if "enum" in spec:
        return "枚举"
    t = spec.get("type")
    if isinstance(t, list):
        return " | ".join(t)
    if t == "array":
        return "array[%s]" % type_text(spec.get("items", {}))
    return t or "?"


def render_props(props, required, def_name=None):
    lines = ["| 字段 | 类型 | 必填 | 说明 |", "| --- | --- | --- | --- |"]
    for name, spec in props.items():
        enum = "（" + " / ".join(spec["enum"]) + "）" if "enum" in spec else ""
        lines.append("| `%s` | %s%s | %s | %s |" % (
            name, type_text(spec), enum, "是" if name in required else "否", note_for(name, def_name)))
    return "\n".join(lines)


def truncate(text, limit=90):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def main():
    schema = load("schema/records.schema.json")
    types = load("registry/entity_types.json")
    relations = load("registry/relations.json")
    vocab = load("registry/vocab.json")
    identity = load("registry/identity_rules.json")
    contract = load("registry/consumer_contract.json")
    constraints = load("schema/constraints.json")
    standards = load("registry/standards_mapping.json")
    roles = load("registry/roles.json")
    defs = schema["$defs"]

    out = []
    out.append("# 文献事实记录协议 v4：可读 schema（按九项组织）\n")
    out.append("本文由 `scripts/render_schema.py` 从 `schema/records.schema.json`、`schema/constraints.json` "
               "与 `registry/*.json` 生成；字段说明为人工注解。**改契约或登记表后重新渲染，不要手改本文。**\n")
    out.append("状态：`%s`，未冻结。校验通过只表示结构与出处自洽，不表示化学结论正确，也不构成准确率。\n"
               % schema["properties"]["schema_version"]["const"])

    out.append("## 九项覆盖（总览）\n")
    out.append("| # | 项 | 落点 | 判定机制 |")
    out.append("| --- | --- | --- | --- |")
    nine = schema.get("x-nine-items") or [
        {"item": num, "title": title, "where": where, "mechanism": how} for num, title, where, how in NINE]
    for item in nine:
        out.append("| %s | %s | %s | %s |" % (item["item"], item["title"], item["where"], item["mechanism"]))
    out.append("")
    out.append("原则：为可判定性设计，不为完整性设计；任何类型、关系、约束都要能被实例检验。"
               "复杂度有显式预算，超预算必须先删再增。\n")

    out.append("模型输入使用schema/extraction.schema.json：每事实仅subject/relation/statement/quote四项必填；内部ID、偏移、审核和图视图由代码处理。后台39类不整包作为模型任务。\n")
    out.append("## 1 实体类型（节点类）\n")
    out.append("实例化规则：%s\n" % types["instantiation_rule"])
    out.append("层级：%s\n" % types["hierarchy_note"])
    out.append("| 类型 | 名称 | 状态 | 判据/正例要点 | 未实例化原因 |")
    out.append("| --- | --- | --- | --- | --- |")
    core_count = 0
    for item in types["types"]:
        if item["status"] == "core":
            core_count += 1
            detail = "；".join(item["criteria"][:2])
        else:
            detail = "—"
        out.append("| `%s` | %s | %s | %s | %s |" % (
            item["type_id"], item["label"], item["status"], truncate(detail),
            truncate(item["blocked_reason"] or "—")))
    out.append("")
    out.append("后台共 %d 类，其中 core %d 类（有判据、可实例化），其余为 proposed（落上去只记候选）。"
               "判据均为本轮新写、`review=pending`，未做标注一致性检验。\n"
               % (len(types["types"]), core_count))

    out.append("## 2 关系签名\n")
    out.append("%s\n" % relations["signature_rule"])
    out.append("%s\n" % relations["cardinality_rule"])
    out.append("| 关系 | 含义 | 状态 | 域 → 值域 | 基数 | 未实例化原因 |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for item in relations["relations"]:
        out.append("| `%s` | %s | %s | %s → %s | %d–%d | %s |" % (
            item["relation_id"], item["label"], item["status"],
            ", ".join(item["domain_types"]) or "—", ", ".join(item["range_types"]) or "—",
            item["cardinality"]["min_participants"], item["cardinality"]["max_participants"],
            truncate(item["blocked_reason"] or "—")))
    out.append("")
    out.append("签名检查只对已登记关系且两侧类型可判的边生效；不匹配进 review 档，保留记录不丢。\n")

    out.append("## 3 标识、合并与拆分\n")
    out.append("%s\n" % identity["scope_note"])
    out.append("| 记录 | ID 形式 | 说明 |")
    out.append("| --- | --- | --- |")
    for item in identity["id_scheme"]:
        out.append("| `%s` | `%s` | %s |" % (item["record"], item["pattern"], item["note"]))
    out.append("")
    for rule in identity["rules"]:
        out.append("- %s" % rule)
    out.append("")
    merge = identity["merge_protocol"]
    out.append("合并/拆分记录 `%s`：same_as 需 %s；distinct_from 需 %s。\n"
               % (merge["record"], "、".join(merge["same_as_requires"]), "、".join(merge["distinct_from_requires"])))
    out.append("禁止：")
    for item in merge["forbidden"]:
        out.append("- %s" % item)
    out.append("")

    out.append("## 4 属性表示边界\n")
    out.append("%s\n" % vocab["representation_policy"]["question"])
    for rule in vocab["representation_policy"]["rules"]:
        out.append("- %s" % rule)
    out.append("")

    out.append("## 5 受控词表与晋升\n")
    out.append("封闭取值（与 `schema/records.schema.json` 的枚举逐项一致，测试会核对）：\n")
    out.append("| 字段 | 取值 |")
    out.append("| --- | --- |")
    for key, values in vocab["closed_sets"].items():
        out.append("| `%s` | %s |" % (key, " / ".join(values)))
    out.append("")
    out.append("功能角色（`role_assignments.functional_role`）：\n")
    out.append("| 选项 | 中文 | 定义 |")
    out.append("| --- | --- | --- |")
    for option in roles["options"]:
        out.append("| `%s` | %s | %s |" % (option["id"], option["zh"], option["definition"]))
    out.append("")
    out.append("| 指标 | 中文 | 家族 | 状态 | 单位提示 |")
    out.append("| --- | --- | --- | --- | --- |")
    for item in vocab["indicators"]:
        out.append("| `%s` | %s | %s | %s | %s |" % (item["id"], item["zh"], item["family_id"],
                                                     item["status"], item["unit_hint"] or "—"))
    out.append("")
    out.append("| 参数 | 中文 | 家族 | 状态 | 是否升实体 |")
    out.append("| --- | --- | --- | --- | --- |")
    for item in vocab["parameters"]:
        out.append("| `%s` | %s | %s | %s | %s |" % (item["id"], item["zh"], item["family_id"],
                                                     item["status"], "否" if not item["entity_worthy"] else "是"))
    out.append("")
    out.append("| 单位原文 | 量纲 | 状态 | 标准 |")
    out.append("| --- | --- | --- | --- |")
    for item in vocab["units"]:
        std = item["standard"]
        out.append("| `%s` | %s | %s | %s（term=%s, %s） |" % (
            item["text"], item["quantity_kind"], item["status"], std["name"],
            std["term"] or "null", std["check_status"]))
    out.append("")
    out.append("晋升：%s。\n" % " / ".join(vocab["promotion"]["states"]))
    for rule in vocab["promotion"]["rules"]:
        out.append("- %s" % rule)
    out.append("")
    out.append("%s\n" % vocab["alias_policy"])

    out.append("## 6 约束与三档处置\n")
    out.append("| 档 | 含义 | 执行点 | 效果 |")
    out.append("| --- | --- | --- | --- |")
    for name, tier in constraints["tiers"].items():
        out.append("| **%s** | %s | %s | %s |" % (name, tier["meaning"], tier["enforcement"], tier["effect"]))
    out.append("")
    out.append("%s\n" % constraints["tier_rule"])
    out.append("| 约束 | 类别 | 档 | 陈述 |")
    out.append("| --- | --- | --- | --- |")
    for item in constraints["constraints"]:
        out.append("| `%s` | %s | %s | %s |" % (item["id"], item["kind"], item["severity"], item["statement"]))
    out.append("")
    out.append("复杂度预算（`scripts/check_budget.py` 超限即失败）：\n")
    out.append("| 指标 | 上限 |")
    out.append("| --- | --- |")
    for key, cap in constraints["budget"].items():
        if key == "rule":
            continue
        out.append("| %s | %s |" % (key, cap))
    out.append("")

    out.append("## 7 上下文与 n-ary\n")
    out.append("一条 `facts` 是有来源的文献陈述（参与者＋条件＋结果＋陈述性质），不等同于一次实际实验，"
               "只有已登记且角色签名明确的关系生成 `edges` 视图；端点方向由角色决定。条件挂在事实上，用 `about_mention_ids` 指明作用对象；"
               "需要限定到具体测量的，用 `outcomes`。\n")
    out.append("程度限定（`outcome.magnitude`）：\n")
    out.append(render_props(defs["magnitude"]["properties"], set(defs["magnitude"]["required"]), "magnitude"))
    out.append("")
    out.append("比较基准（`outcome.comparison`）：\n")
    out.append(render_props(defs["comparison"]["properties"], set(defs["comparison"]["required"]), "comparison"))
    out.append("")
    out.append("边不得自带新语义：`qualifiers` 与 `evidence`、`review` 必须与来源事实完全一致，"
               "不一致即 block（`EDGE_SEMANTICS_DRIFT`）。\n")

    out.append("## 8 溯源与可信度\n")
    out.append("| 维度 | 字段 | 说明 |")
    out.append("| --- | --- | --- |")
    provenance = [
        ("来源文档", "documents.sha256 / blocks.text", "引用必须逐字命中块内片段或表格单元格"),
        ("陈述性质", "facts.statement_type", "观测/计算结果/作者解释/未来工作/转述/未知"),
        ("来源范围", "facts.source_scope", "本研究/引用他人/综述归纳/未知"),
        ("肯定与否定", "facts.polarity", "含 negated / no_effect，不把“无效应”写成缺失"),
        ("语气", "facts.modality", "explicit / hedged / speculative / unknown"),
        ("转述目标", "facts.cited_work", "指称＋可解析文献；未转述时显式 null"),
        ("抽取方式", "facts.extraction", "方法/模型/协议版本，规则映射时 model=null"),
        ("未报告", "value_kind=absent / unit_status=not_reported", "用状态表示缺失，不用空值或占位串"),
        ("不确定", "value_kind=qualitative / magnitude=unknown / comparison=not_stated", "不确定本身可被查询"),
    ]
    for dim, field, desc in provenance:
        out.append("| %s | `%s` | %s |" % (dim, field, desc))
    out.append("")
    out.append("pending仅代表尚未人工审核，不自动禁止引用或候选分析；具体数值操作另核对对象、单位与口径。\n")

    out.append("## 9 演化与治理\n")
    out.append("- 版本号：`schema_version` 为 `%s`；改契约同时改 `$id` 与 `schema_version`，旧记录先迁移再入库。\n"
               % schema["properties"]["schema_version"]["const"])
    out.append("- 迁移：只增字段先发新 schema 版本；删除/改名必须走 `deprecated` 状态并保留映射，不重命名历史 id。")
    out.append("- 晋升：候选只能在 `vocab.promotion` 的四个状态间前进，晋升需依据（原文偏移或核验记录），"
               "只改 status 不算晋升。")
    out.append("- 预算：%s；超预算先删再增。" % constraints["budget"]["rule"])
    out.append("- 审计：`scripts/check_budget.py` 查预算与档位；`tests/` 查枚举一致性、档位覆盖、物化确定性；"
               "`scripts/render_schema.py` 保证文档与实现同步。")
    out.append("- 命名：按 `registry/identity_rules.json` 的 id_scheme；物化 id 一律派生，不手工编辑。\n")

    out.append("## 消费端契约\n")
    out.append("检索键（`scripts/materialize.py` 的 `retrieval_keys()` 生成）：\n")
    out.append("| 键 | 来源 | 说明 |")
    out.append("| --- | --- | --- |")
    for item in contract["retrieval_keys"]:
        out.append("| `%s` | %s | %s |" % (item["key"], item["source"], item["definition"]))
    out.append("")
    out.append("按用途独立判断：\n")
    out.append("| 用途 | 规则 |")
    out.append("| --- | --- |")
    for name, item in contract["capabilities"].items():
        out.append("| %s | %s |" % (name, item["rule"]))


    out.append("## 复用成熟标准\n")
    out.append("%s\n" % standards["note"])
    out.append("| 标准 | 用到部分 | 我们的字段 | 状态 |")
    out.append("| --- | --- | --- | --- |")
    for item in standards["mappings"]:
        out.append("| %s | %s | %s | %s |" % (item["standard"], item["part"],
                                              ", ".join("`%s`" % f for f in item["our_fields"]), item["status"]))
    out.append("")
    out.append("%s\n" % standards["reuse_policy"])

    out.append("## 记录定义\n")
    out.append("| 记录 | 说明 | 必填 |")
    out.append("| --- | --- | --- |")
    required_top = set(schema.get("required") or [])
    for key, note in BUNDLE_NOTE.items():
        if key in schema["properties"]:
            out.append("| `%s` | %s | %s |" % (key, note, "是" if key in required_top else "否"))
    out.append("")
    for key, note in BUNDLE_NOTE.items():
        if key not in schema["properties"]:
            continue
        ref = schema["properties"][key].get("items", {}).get("$ref", "").split("/")[-1]
        if ref not in defs:
            continue
        out.append("### `%s`（`$defs/%s`）\n" % (key, ref))
        out.append(note + "\n")
        out.append(render_props(defs[ref]["properties"], set(defs[ref].get("required") or []), ref))
        out.append("")
    out.append("### 嵌套记录\n")
    for name in NESTED_DEFS:
        if name not in defs:
            continue
        out.append("**`%s`**\n" % name)
        out.append(render_props(defs[name]["properties"], set(defs[name].get("required") or []), name))
        out.append("")

    out.append("## 未实现与已知限制\n")
    out.append("- 冲突、共识、推荐窗口等聚合层：属消费层，尚未实现。")
    out.append("- 别名与结构消歧、外部库合并：按用户要求暂缓；`identities` 仅为候选，不用 InChIKey 冒充全局身份。")
    out.append("- 单位只保留原文串与状态，未做换算；QUDT 局部名未核对。")
    out.append("- 全库事实抽取、抽取准确率、问答效果：未做，不做准确率承诺。")
    out.append("- 多级表头与脚注的条件继承仍需抽取侧处理，本协议只校验单元格取值。\n")

    path = ROOT / "schema/schema.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    sections = sum(1 for line in out if line.startswith("## "))
    print(json.dumps({"output": "schema/schema.md", "sections": sections,
                      "core_types": core_count, "relations": len(relations["relations"]),
                      "codes_in_catalog": sum(len(item["codes"]) for item in constraints["constraints"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
